from __future__ import annotations

import json
import multiprocessing
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

from app.asset_loader import ReviewAssetLoader
from app.llm_client import LlmRequestError
from app.llm_client import _extract_message_content, _parse_json_content
from app.models import build_clause_record, build_evidence_item_record, build_risk_item_record
from app.parser_worker import ParseWorker
from app.result_aggregator import build_report_markdown
from app.result_presenter import group_risks
from app.repository import JsonRepository
from app.result_aggregator import ResultAggregator
from app.review_assembler import ReviewInputAssembler
from app.result_aggregator import build_overall_conclusion
from app.review_executor import (
    ReviewExecutor,
    _build_batch_payload,
    _classify_clause_business_modules,
    _chunk_clauses_for_review,
    _normalize_finding_rule_code,
    _next_retry_clause_max_chars,
    _select_candidate_clauses,
    _select_rule_candidate_clause_map,
    _select_rules_for_clause_batch,
)
from app.upload_service import UploadFile, UploadService
from app.worker_runner import WorkerRunner
from tests.llm_test_support import fake_llm_environment


def build_minimal_docx(text_lines: list[str]) -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in text_lines)
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body>"
        "</w:document>"
    )
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def build_docx_with_table(paragraph_lines: list[str], table_rows: list[list[str]]) -> bytes:
    paragraphs = "".join(f"<w:p><w:r><w:t>{line}</w:t></w:r></w:p>" for line in paragraph_lines)
    rows = []
    for row in table_rows:
        cells = "".join(
            f"<w:tc><w:p><w:r><w:t>{cell}</w:t></w:r></w:p></w:tc>"
            for cell in row
        )
        rows.append(f"<w:tr>{cells}</w:tr>")
    table_xml = f"<w:tbl>{''.join(rows)}</w:tbl>" if rows else ""
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{paragraphs}{table_xml}</w:body>"
        "</w:document>"
    )
    buffer = BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def build_minimal_pdf(text_lines: list[str]) -> bytes:
    operations = " ".join(f"({line}) Tj" for line in text_lines)
    return (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Count 1 /Kids [3 0 R] >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R >> endobj\n"
        b"4 0 obj << /Length 64 >> stream\n"
        + operations.encode("utf-8", errors="ignore")
        + b"\nendstream endobj\ntrailer << /Root 1 0 R >>\n%%EOF"
    )


def save_clause_batch(runtime_dir: str, prefix: str, total: int) -> None:
    repository = JsonRepository(Path(runtime_dir))
    for index in range(total):
        repository.save_clause(
            build_clause_record(
                clause_id=f"{prefix}_{index}",
                document_id="document_shared",
                chapter_id="chapter_shared",
                chapter_title="第一章 测试章节",
                clause_order=index + 1,
                clause_text=f"测试条款 {prefix}-{index}",
                location_label=f"第一章 测试章节 / {prefix}-{index}",
                clause_type="条款片段",
            )
        )


class ParseWorkerTestCase(unittest.TestCase):
    def test_llm_client_extracts_reasoning_when_content_is_null(self):
        payload = {
            "choices": [
                {
                    "message": {
                        "content": None,
                        "reasoning": "Thinking Process:\\n\\n最终输出：\\n{\"findings\":[]}",
                    }
                }
            ]
        }

        content = _extract_message_content(payload)

        self.assertIn("{\"findings\":[]}", content)

    def test_llm_client_parses_embedded_json_from_reasoning_text(self):
        content = (
            "Thinking Process:\\n"
            "1. 分析输入。\\n"
            "2. 形成输出。\\n"
            "最终输出：\\n"
            "{\"findings\":[{\"rule_code\":\"R1\",\"clause_id\":\"c1\"}]}"
        )

        parsed = _parse_json_content(content)

        self.assertIn("findings", parsed)
        self.assertEqual(parsed["findings"][0]["rule_code"], "R1")

    def test_repository_keeps_json_valid_under_multi_process_clause_writes(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            process_context = multiprocessing.get_context("fork")
            process_a = process_context.Process(
                target=save_clause_batch,
                args=(runtime_dir, "worker_a", 80),
            )
            process_b = process_context.Process(
                target=save_clause_batch,
                args=(runtime_dir, "worker_b", 80),
            )

            process_a.start()
            process_b.start()
            process_a.join(timeout=10)
            process_b.join(timeout=10)

            self.assertEqual(process_a.exitcode, 0)
            self.assertEqual(process_b.exitcode, 0)

            clauses_path = Path(runtime_dir) / "metadata" / "clauses.json"
            clauses = json.loads(clauses_path.read_text(encoding="utf-8"))
            self.assertEqual(len(clauses), 160)

    def test_build_report_markdown_sorts_risks_by_severity_for_display(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            low_risk = build_risk_item_record(
                risk_id="risk_low",
                task_id="task_001",
                project_id="project_001",
                document_id="document_001",
                clause_id="clause_001",
                rule={
                    "rule_id": "rule_low",
                    "rule_name": "低风险规则",
                    "risk_level": "低",
                    "execution_level": "辅助提示",
                    "rule_domain": "采购需求",
                    "file_module": "采购需求",
                },
                location_label="第二章 评分办法 / 2.1 评分标准",
                risk_description="低风险说明",
                review_reasoning="当前最小执行骨架在“第二章 评分办法 / 2.1 评分标准”识别到关键词“酌情”，属于第二章 评分办法的段落片段。",
            )
            high_risk = build_risk_item_record(
                risk_id="risk_high",
                task_id="task_001",
                project_id="project_001",
                document_id="document_001",
                clause_id="clause_002",
                rule={
                    "rule_id": "rule_high",
                    "rule_name": "高风险规则",
                    "risk_level": "高",
                    "execution_level": "自动判定",
                    "rule_domain": "资格条件",
                    "file_module": "资格条件",
                },
                location_label="第一章 资格要求 / 1.1 供应商资格",
                risk_description="高风险说明",
                review_reasoning="当前最小执行骨架在“第一章 资格要求 / 1.1 供应商资格”识别到关键词“本地注册”，属于第一章 资格要求的条款片段。",
            )
            low_risk.created_at = "2026-03-29T10:00:02+08:00"
            high_risk.created_at = "2026-03-29T10:00:01+08:00"
            repository.save_evidence(
                build_evidence_item_record(
                    evidence_id="evidence_high",
                    risk_id="risk_high",
                    document_id="document_001",
                    clause_id="clause_002",
                    quoted_text="供应商须本地注册并在本地办公。",
                    location_label="第一章 资格要求 / 1.1 供应商资格",
                    evidence_note="原文证据来自资格条款。",
                )
            )

            risk_groups = group_risks(risks=[low_risk, high_risk], repository=repository)
            markdown = build_report_markdown(
                file_name="招标文件.docx",
                overall_conclusion="测试结论",
                risk_groups=risk_groups,
            )

            self.assertLess(markdown.index("高风险规则"), markdown.index("低风险规则"))
            self.assertIn("- 章节上下文：第一章 资格要求", markdown)
            self.assertIn("- 业务单元：未标注", markdown)
            self.assertIn("- 片段类型：条款片段", markdown)
            self.assertIn("- 规则编号：rule_high", markdown)
            self.assertIn("### 风险组 1", markdown)
            self.assertIn("- 归并命中数：1", markdown)

    def test_group_risks_polishes_titles_and_location_for_readability(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            clause = build_clause_record(
                clause_id="clause_contract",
                document_id="document_001",
                chapter_id="chapter_001",
                chapter_title=(
                    "九、 合同文本要求按规定格式打印，大小为 A4 幅面（高 297 毫米，宽 210毫米），"
                    "竖装。左边为装订边，正文内容所用字型应不小于 5 号字。"
                ),
                clause_order=1,
                clause_text="因财政下达资金情况无法明确，终验款将按照财政向甲方下达的项目资金情况进行据实支付。",
                location_label=(
                    "九、 合同文本要求按规定格式打印，大小为 A4 幅面（高 297 毫米，宽 210毫米），"
                    "竖装。左边为装订边，正文内容所用字型应不小于 5 号字。 / 第四条 终验阶段"
                ),
                module_type="合同条款",
                unit_type="合同项",
                unit_label="付款条款",
                unit_name="第四条 终验阶段",
                clause_type="条款片段",
            )
            repository.save_clause(clause)
            risk = build_risk_item_record(
                risk_id="risk_contract",
                task_id="task_001",
                project_id="project_001",
                document_id="document_001",
                clause_id="clause_contract",
                rule={
                    "rule_id": "rule_v1_r12",
                    "rule_name": "关键条款缺失/责任失衡检查",
                    "risk_level": "高",
                    "execution_level": "自动判定",
                    "rule_domain": "合同与履约风险规则",
                    "file_module": "合同条款",
                },
                location_label=clause.location_label,
                risk_description="合同条款疑似责任失衡。",
                review_reasoning="模型判断合同付款义务与财政到款挂钩。",
                risk_title="关键条款缺失/责任失衡检查",
            )
            repository.save_evidence(
                build_evidence_item_record(
                    evidence_id="evidence_contract",
                    risk_id="risk_contract",
                    document_id="document_001",
                    clause_id="clause_contract",
                    quoted_text="终验款将按照财政向甲方下达的项目资金情况进行据实支付。",
                    location_label=clause.location_label,
                    evidence_note="合同付款条款原文证据。",
                )
            )

            risk_groups = group_risks(risks=[risk], repository=repository)

            self.assertEqual(risk_groups[0]["risk_title"], "付款条件与财政资金挂钩，存在回款责任失衡风险")
            self.assertIn("...", risk_groups[0]["location_label"])
            self.assertIn("...", risk_groups[0]["chapter_title"])

    def test_build_overall_conclusion_uses_current_focus_areas(self):
        conclusion = build_overall_conclusion(
            risk_groups=[
                {
                    "rule_code": "R12",
                    "risk_title": "付款条件与财政资金挂钩，存在回款责任失衡风险",
                    "unit_label": "付款条款",
                },
                {
                    "rule_code": "R9",
                    "risk_title": "评分标准量化不足，自由裁量空间较大",
                    "unit_label": "单个评分项",
                },
            ],
            risk_count_high=2,
            risk_count_medium=0,
            risk_count_low=0,
        )

        self.assertIn("合同付款条款和评分细则", conclusion)
        self.assertNotIn("品牌指向", conclusion)

    def test_group_risks_distinguishes_contract_risk_titles_by_evidence(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            clause_payment = build_clause_record(
                clause_id="clause_payment",
                document_id="document_001",
                chapter_id="chapter_001",
                chapter_title="第九章 合同条款",
                clause_order=1,
                clause_text="因财政下达资金情况无法明确，终验款将按照财政向甲方下达的项目资金情况进行据实支付。",
                location_label="第九章 合同条款 / 第四条 终验阶段",
                module_type="合同条款",
                unit_type="合同项",
                unit_label="付款条款",
                unit_name="第四条 终验阶段",
                clause_type="条款片段",
            )
            clause_penalty = build_clause_record(
                clause_id="clause_penalty",
                document_id="document_001",
                chapter_id="chapter_001",
                chapter_title="第九章 合同条款",
                clause_order=2,
                clause_text="乙方应当赔偿损失，并向甲方支付合同总额30%的违约金。",
                location_label="第九章 合同条款 / 违约责任",
                module_type="合同条款",
                unit_type="合同项",
                unit_label="违约责任条款",
                unit_name="违约责任",
                clause_type="条款片段",
            )
            repository.save_clause(clause_payment)
            repository.save_clause(clause_penalty)

            payment_risk = build_risk_item_record(
                risk_id="risk_payment",
                task_id="task_001",
                project_id="project_001",
                document_id="document_001",
                clause_id="clause_payment",
                rule={
                    "rule_id": "rule_v1_r12",
                    "rule_name": "关键条款缺失/责任失衡检查",
                    "risk_level": "高",
                    "execution_level": "自动判定",
                    "rule_domain": "合同与履约风险规则",
                    "file_module": "合同条款",
                },
                location_label=clause_payment.location_label,
                risk_description="付款责任失衡。",
                review_reasoning="模型判断付款条件受财政下达资金影响。",
                risk_title="关键条款缺失/责任失衡检查",
            )
            penalty_risk = build_risk_item_record(
                risk_id="risk_penalty",
                task_id="task_001",
                project_id="project_001",
                document_id="document_001",
                clause_id="clause_penalty",
                rule={
                    "rule_id": "rule_v1_r12",
                    "rule_name": "关键条款缺失/责任失衡检查",
                    "risk_level": "高",
                    "execution_level": "自动判定",
                    "rule_domain": "合同与履约风险规则",
                    "file_module": "合同条款",
                },
                location_label=clause_penalty.location_label,
                risk_description="违约责任偏重。",
                review_reasoning="模型判断违约责任明显偏重。",
                risk_title="关键条款缺失/责任失衡检查",
            )
            repository.save_evidence(
                build_evidence_item_record(
                    evidence_id="evidence_payment",
                    risk_id="risk_payment",
                    document_id="document_001",
                    clause_id="clause_payment",
                    quoted_text="终验款将按照财政向甲方下达的项目资金情况进行据实支付。",
                    location_label=clause_payment.location_label,
                    evidence_note="付款条款证据。",
                )
            )
            repository.save_evidence(
                build_evidence_item_record(
                    evidence_id="evidence_penalty",
                    risk_id="risk_penalty",
                    document_id="document_001",
                    clause_id="clause_penalty",
                    quoted_text="向甲方支付合同总额30%的违约金。",
                    location_label=clause_penalty.location_label,
                    evidence_note="违约责任条款证据。",
                )
            )

            risk_groups = group_risks(risks=[payment_risk, penalty_risk], repository=repository)

            self.assertEqual(risk_groups[0]["risk_title"], "付款条件与财政资金挂钩，存在回款责任失衡风险")
            self.assertEqual(risk_groups[1]["risk_title"], "违约责任明显偏重，存在合同失衡风险")

    def test_group_risks_refines_uncertain_r9_unit_label(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            clause = build_clause_record(
                clause_id="clause_score",
                document_id="document_001",
                chapter_id="chapter_001",
                chapter_title="第五章 评分办法",
                clause_order=1,
                clause_text="①评审为优的最高得40分；②评审为良的最高得20分。",
                location_label="第五章 评分办法 / 售后服务及培训方案评价",
                module_type="其他",
                unit_type="条款",
                unit_label="不确定审查对象",
                unit_name="售后服务及培训方案评价",
                clause_type="条款片段",
            )
            repository.save_clause(clause)
            risk = build_risk_item_record(
                risk_id="risk_score",
                task_id="task_001",
                project_id="project_001",
                document_id="document_001",
                clause_id="clause_score",
                rule={
                    "rule_id": "rule_v1_r9",
                    "rule_name": "评分项未量化检查",
                    "risk_level": "高",
                    "execution_level": "自动判定",
                    "rule_domain": "评审可解释性规则",
                    "file_module": "评分办法",
                },
                location_label=clause.location_label,
                risk_description="评分标准量化不足。",
                review_reasoning="模型判断评分标准存在自由裁量空间。",
                risk_title="评分标准量化不足，存在自由裁量权过大风险",
            )
            repository.save_evidence(
                build_evidence_item_record(
                    evidence_id="evidence_score",
                    risk_id="risk_score",
                    document_id="document_001",
                    clause_id="clause_score",
                    quoted_text="①评审为优的最高得40分；②评审为良的最高得20分。",
                    location_label=clause.location_label,
                    evidence_note="评分项证据。",
                )
            )

            risk_groups = group_risks(risks=[risk], repository=repository)

            self.assertEqual(risk_groups[0]["unit_label"], "单个评分项（售后服务及培训方案评价）")

    def test_group_risks_merges_same_clause_and_rule_duplicates(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            risk_a = build_risk_item_record(
                risk_id="risk_a",
                task_id="task_001",
                project_id="project_001",
                document_id="document_001",
                clause_id="clause_001",
                rule={
                    "rule_id": "rule_r3",
                    "rule_name": "资格条件过高检查",
                    "risk_level": "中",
                    "execution_level": "辅助提示",
                    "rule_domain": "合法性规则",
                    "file_module": "资格条件",
                },
                location_label="第三章 商务要求 / 3.1 供应商认证情况",
                risk_description="要求厂家认证讲师，可能抬高资格门槛。",
                review_reasoning="当前最小执行骨架识别到厂家认证讲师表述，属于第三章 商务要求的条款片段。",
            )
            risk_b = build_risk_item_record(
                risk_id="risk_b",
                task_id="task_001",
                project_id="project_001",
                document_id="document_001",
                clause_id="clause_001",
                rule={
                    "rule_id": "rule_r3",
                    "rule_name": "资格条件过高检查",
                    "risk_level": "中",
                    "execution_level": "辅助提示",
                    "rule_domain": "合法性规则",
                    "file_module": "资格条件",
                },
                location_label="第三章 商务要求 / 3.1 供应商认证情况",
                risk_description="要求执业医师证，可能抬高资格门槛。",
                review_reasoning="当前最小执行骨架识别到执业医师证表述，属于第三章 商务要求的条款片段。",
            )
            repository.save_evidence(
                build_evidence_item_record(
                    evidence_id="evidence_a",
                    risk_id="risk_a",
                    document_id="document_001",
                    clause_id="clause_001",
                    quoted_text="培训人员团队为厂家认证讲师。",
                    location_label="第三章 商务要求 / 3.1 供应商认证情况",
                    evidence_note="原文证据命中厂家认证讲师。",
                )
            )
            repository.save_evidence(
                build_evidence_item_record(
                    evidence_id="evidence_b",
                    risk_id="risk_b",
                    document_id="document_001",
                    clause_id="clause_001",
                    quoted_text="培训人员团队为具有执业医师证的临床医生。",
                    location_label="第三章 商务要求 / 3.1 供应商认证情况",
                    evidence_note="原文证据命中执业医师证。",
                )
            )

            risk_groups = group_risks(risks=[risk_a, risk_b], repository=repository)

            self.assertEqual(len(risk_groups), 1)
            self.assertEqual(risk_groups[0]["merged_hit_count"], 2)
            self.assertIn("厂家认证讲师", str(risk_groups[0]["risk_description"]))
            self.assertIn("执业医师证", str(risk_groups[0]["risk_description"]))

    def test_group_risks_merges_same_location_and_rule_duplicates(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            base_rule = {
                "rule_id": "rule_r9",
                "rule_name": "评分项未量化检查",
                "risk_level": "高",
                "execution_level": "自动判定",
                "rule_domain": "评审可解释性规则",
                "file_module": "评分办法",
            }
            risk_a = build_risk_item_record(
                risk_id="risk_a",
                task_id="task_001",
                project_id="project_001",
                document_id="document_001",
                clause_id="clause_001",
                rule=base_rule,
                location_label="第二章 评分办法 / 2.1 评分标准",
                risk_description="评分条款存在优良中差表述，缺少量化标准。",
                review_reasoning="当前最小执行骨架识别到优良中差表述，属于第二章 评分办法的条款片段。",
            )
            risk_b = build_risk_item_record(
                risk_id="risk_b",
                task_id="task_001",
                project_id="project_001",
                document_id="document_001",
                clause_id="clause_002",
                rule=base_rule,
                location_label="第二章 评分办法 / 2.1 评分标准",
                risk_description="评分条款以优良中差酌情打分，量化口径不足。",
                review_reasoning="当前最小执行骨架识别到酌情打分表述，属于第二章 评分办法的条款片段。",
            )

            risk_groups = group_risks(risks=[risk_a, risk_b], repository=repository)

            self.assertEqual(len(risk_groups), 1)
            self.assertEqual(risk_groups[0]["merged_hit_count"], 2)

    def test_group_risks_prefers_clause_metadata_for_display_fields(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            repository.save_clause(
                build_clause_record(
                    clause_id="clause_001",
                    document_id="document_001",
                    chapter_id="chapter_001",
                    chapter_title="第五章 商务要求",
                    clause_order=1,
                    clause_text="★原厂保修，货物免费保修期 5 年。",
                    location_label="第五章 商务要求 / 免费保修期 / ★原厂保修",
                    module_type="合同条款",
                    unit_type="商务项",
                    unit_label="商务要求项",
                    unit_name="免费保修期",
                    clause_type="条款片段",
                )
            )
            risk = build_risk_item_record(
                risk_id="risk_r3",
                task_id="task_001",
                project_id="project_001",
                document_id="document_001",
                clause_id="clause_001",
                rule={
                    "rule_id": "R3",
                    "rule_name": "资格条件过高检查",
                    "risk_level": "中",
                    "execution_level": "辅助提示",
                    "rule_domain": "合法性规则",
                    "file_module": "资格条件",
                },
                location_label="第五章 商务要求 / 免费保修期 / ★原厂保修，货物免费保修期 5 年。",
                risk_description="原厂保修要求可能抬高竞争门槛。",
                review_reasoning="业务单元：商务要求项（截断示例），属于第五章 商务要求的条款片段。",
            )

            risk_groups = group_risks(risks=[risk], repository=repository)

            self.assertEqual(risk_groups[0]["chapter_title"], "第五章 商务要求")
            self.assertEqual(risk_groups[0]["unit_label"], "商务要求项（免费保修期）")
            self.assertEqual(risk_groups[0]["rule_code"], "R3")
            self.assertEqual(risk_groups[0]["location_label"], "第五章 商务要求 / 免费保修期 / ★原厂保修")

    def test_group_risks_hides_uncertain_r3_when_specific_r3_exists(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            repository.save_clause(
                build_clause_record(
                    clause_id="clause_specific",
                    document_id="document_001",
                    chapter_id="chapter_001",
                    chapter_title="第五章 商务要求",
                    clause_order=1,
                    clause_text="★原厂保修，货物免费保修期 5 年。",
                    location_label="第五章 商务要求 / 免费保修期",
                    module_type="合同条款",
                    unit_type="商务项",
                    unit_label="商务要求项",
                    unit_name="免费保修期",
                    clause_type="条款片段",
                )
            )
            repository.save_clause(
                build_clause_record(
                    clause_id="clause_uncertain",
                    document_id="document_001",
                    chapter_id="chapter_002",
                    chapter_title="附件评分表",
                    clause_order=2,
                    clause_text="投标人具备非金属矿采矿许可证。",
                    location_label="附件评分表 / 专家打分",
                    module_type="其他",
                    unit_type="条款",
                    unit_label="不确定审查对象",
                    unit_name="专家打分",
                    clause_type="条款片段",
                )
            )
            rule = {
                "rule_id": "R3",
                "rule_name": "资格条件过高检查",
                "risk_level": "中",
                "execution_level": "辅助提示",
                "rule_domain": "合法性规则",
                "file_module": "资格条件",
            }
            specific_risk = build_risk_item_record(
                risk_id="risk_specific",
                task_id="task_001",
                project_id="project_001",
                document_id="document_001",
                clause_id="clause_specific",
                rule=rule,
                location_label="第五章 商务要求 / 免费保修期",
                risk_description="原厂保修要求可能抬高竞争门槛。",
                review_reasoning="业务单元：商务要求项，属于第五章 商务要求的条款片段。",
            )
            uncertain_risk = build_risk_item_record(
                risk_id="risk_uncertain",
                task_id="task_001",
                project_id="project_001",
                document_id="document_001",
                clause_id="clause_uncertain",
                rule=rule,
                location_label="附件评分表 / 专家打分",
                risk_description="存在无关资质要求。",
                review_reasoning="业务单元：不确定审查对象，属于附件评分表的条款片段。",
            )

            risk_groups = group_risks(risks=[specific_risk, uncertain_risk], repository=repository)

            self.assertEqual(len(risk_groups), 1)
            self.assertEqual(risk_groups[0]["risk_id"], "risk_specific")

    def test_parse_worker_consumes_queue_and_marks_task_review_queued(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            upload_service = UploadService(repository)
            upload_response = upload_service.create_review_task(
                UploadFile(
                    filename="招标文件.docx",
                    content=build_minimal_docx(
                        [
                            "第一章 总则",
                            "1.1 项目概况",
                            "本项目用于测试。",
                            "第二章 评分办法",
                            "2.1 评分标准",
                            "综合评价。",
                        ]
                    ),
                )
            )

            processed_count = ParseWorker(repository).run_pending_jobs()

            self.assertEqual(processed_count, 1)
            task = repository.get_task(upload_response["task_id"])
            self.assertIsNotNone(task)
            self.assertEqual(task.internal_status, "review_queued")
            document = repository.get_document(task.document_id)
            self.assertEqual(document.parsed_status, "parsed")

            chapters = json.loads((Path(runtime_dir) / "metadata" / "chapters.json").read_text(encoding="utf-8"))
            clauses = json.loads((Path(runtime_dir) / "metadata" / "clauses.json").read_text(encoding="utf-8"))
            blocks = json.loads((Path(runtime_dir) / "metadata" / "blocks.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(chapters), 2)
            self.assertGreaterEqual(len(clauses), 2)
            self.assertGreaterEqual(len(blocks), 4)
            self.assertEqual(list((Path(runtime_dir) / "queues" / "parse").glob("*.json")), [])
            self.assertEqual(len(list((Path(runtime_dir) / "queues" / "review").glob("*.json"))), 1)

    def test_parse_worker_extracts_text_from_pdf(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            upload_service = UploadService(repository)
            upload_response = upload_service.create_review_task(
                UploadFile(
                    filename="招标文件.pdf",
                    content=build_minimal_pdf(
                        [
                            "第一章 资格要求",
                            "1.1 供应商资格",
                            "供应商须具备独立承担民事责任的能力。",
                            "第二章 评分办法",
                            "2.1 评分标准",
                            "采用综合评价法。",
                        ]
                    ),
                )
            )

            ParseWorker(repository).run_pending_jobs()

            task = repository.get_task(upload_response["task_id"])
            self.assertIsNotNone(task)
            self.assertEqual(task.internal_status, "review_queued")
            document = repository.get_document(task.document_id)
            self.assertIsNotNone(document)
            assert document is not None
            self.assertIn("供应商须具备独立承担民事责任的能力", document.raw_text)

    def test_parse_worker_keeps_multilevel_numbered_lines_as_clauses(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            upload_service = UploadService(repository)
            upload_response = upload_service.create_review_task(
                UploadFile(
                    filename="招标文件.docx",
                    content=build_minimal_docx(
                        [
                            "第一章 资格要求",
                            "1.1 供应商资格",
                            "供应商须具备独立承担民事责任的能力。",
                            "1.2 信用要求",
                            "供应商不得存在严重违法失信记录。",
                        ]
                    ),
                )
            )

            ParseWorker(repository).run_pending_jobs()

            task = repository.get_task(upload_response["task_id"])
            self.assertIsNotNone(task)
            assert task is not None
            self.assertEqual(task.internal_status, "review_queued")

            blocks = repository.list_blocks_by_document(task.document_id)
            section_titles = [block.title for block in blocks if block.block_type == "section"]
            clause_titles = [block.title for block in blocks if block.block_type == "clause"]

            self.assertIn("第一章 资格要求", section_titles)
            self.assertNotIn("1.1 供应商资格", section_titles)
            self.assertNotIn("1.2 信用要求", section_titles)
            self.assertIn("1.1 供应商资格", clause_titles)
            self.assertIn("1.2 信用要求", clause_titles)

    def test_parse_worker_filters_toc_like_lines_and_preserves_body(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            upload_service = UploadService(repository)
            upload_response = upload_service.create_review_task(
                UploadFile(
                    filename="招标文件.docx",
                    content=build_minimal_docx(
                        [
                            "目录",
                            "第一章 资格要求 .......... 1",
                            "第二章 评分办法 .......... 5",
                            "第一章 资格要求",
                            "1.1 供应商资格",
                            "供应商须具备独立承担民事责任的能力。",
                        ]
                    ),
                )
            )

            ParseWorker(repository).run_pending_jobs()

            task = repository.get_task(upload_response["task_id"])
            self.assertIsNotNone(task)
            assert task is not None
            self.assertEqual(task.internal_status, "review_queued")
            document = repository.get_document(task.document_id)
            assert document is not None
            self.assertNotIn("第一章 资格要求 .......... 1", document.raw_text)
            self.assertNotIn("第二章 评分办法 .......... 5", document.raw_text)
            self.assertIn("供应商须具备独立承担民事责任的能力。", document.raw_text)

    def test_parse_worker_extracts_docx_table_text_into_reviewable_content(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            upload_service = UploadService(repository)
            upload_response = upload_service.create_review_task(
                UploadFile(
                    filename="招标文件.docx",
                    content=build_docx_with_table(
                        ["第一章 采购需求", "1.1 供货要求"],
                        [["评分项", "综合评价"], ["资格项", "供应商须本地注册"]],
                    ),
                )
            )

            ParseWorker(repository).run_pending_jobs()

            task = repository.get_task(upload_response["task_id"])
            self.assertIsNotNone(task)
            assert task is not None
            self.assertEqual(task.internal_status, "review_queued")
            document = repository.get_document(task.document_id)
            assert document is not None
            self.assertIn("评分项 | 综合评价", document.raw_text)
            self.assertIn("资格项 | 供应商须本地注册", document.raw_text)
            self.assertEqual(document.raw_text.count("评分项 | 综合评价"), 1)
            self.assertEqual(document.raw_text.count("资格项 | 供应商须本地注册"), 1)
            clauses = repository.list_clauses_by_document(task.document_id)
            self.assertTrue(any(clause.unit_type == "参数项" for clause in clauses))
            self.assertTrue(all(clause.module_type == "采购需求" for clause in clauses))

    def test_parse_worker_classifies_score_table_rows_as_review_items(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            upload_service = UploadService(repository)
            upload_response = upload_service.create_review_task(
                UploadFile(
                    filename="招标文件.docx",
                    content=build_docx_with_table(
                        ["第二章 评分办法", "2.1 评分标准"],
                        [["评分项", "综合评价"], ["分值", "20 分"]],
                    ),
                )
            )

            ParseWorker(repository).run_pending_jobs()

            task = repository.get_task(upload_response["task_id"])
            assert task is not None
            clauses = repository.list_clauses_by_document(task.document_id)

            self.assertTrue(any(clause.module_type == "评分办法" for clause in clauses))
            self.assertTrue(any(clause.unit_type == "评分项" for clause in clauses))

    def test_parse_worker_builds_chapter_text_and_location_label_for_review(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            upload_service = UploadService(repository)
            upload_response = upload_service.create_review_task(
                UploadFile(
                    filename="招标文件.docx",
                    content=build_minimal_docx(
                        [
                            "第一章 资格要求",
                            "1.1 供应商资格",
                            "供应商须具备独立承担民事责任的能力。",
                            "1.2 信用要求",
                            "供应商不得存在严重违法失信记录。",
                        ]
                    ),
                )
            )

            ParseWorker(repository).run_pending_jobs()

            task = repository.get_task(upload_response["task_id"])
            assert task is not None
            chapters = json.loads((Path(runtime_dir) / "metadata" / "chapters.json").read_text(encoding="utf-8"))
            clauses = json.loads((Path(runtime_dir) / "metadata" / "clauses.json").read_text(encoding="utf-8"))
            chapter_texts = [payload["chapter_text"] for payload in chapters.values()]
            clause_locations = [payload["location_label"] for payload in clauses.values()]
            clause_types = [payload["clause_type"] for payload in clauses.values()]
            clause_chapter_titles = [payload["chapter_title"] for payload in clauses.values()]
            module_types = [payload["module_type"] for payload in clauses.values()]
            unit_types = [payload["unit_type"] for payload in clauses.values()]

            self.assertTrue(any("供应商须具备独立承担民事责任的能力。" in text for text in chapter_texts))
            self.assertTrue(any(location.startswith("第一章 资格要求 / 1.1 供应商资格") for location in clause_locations))
            self.assertIn("条款片段", clause_types)
            self.assertTrue(all(title == "第一章 资格要求" for title in clause_chapter_titles))
            self.assertTrue(all(module_type == "资格条件" for module_type in module_types))
            self.assertTrue(all(unit_type == "条款" for unit_type in unit_types))

    def test_parse_worker_suppresses_exact_duplicate_clauses(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            upload_service = UploadService(repository)
            upload_response = upload_service.create_review_task(
                UploadFile(
                    filename="招标文件.docx",
                    content=build_minimal_docx(
                        [
                            "第一章 技术要求",
                            "1.1 产品参数",
                            "内窥镜主机须支持高清成像。",
                            "1.1 产品参数",
                            "内窥镜主机须支持高清成像。",
                        ]
                    ),
                )
            )

            ParseWorker(repository).run_pending_jobs()

            task = repository.get_task(upload_response["task_id"])
            assert task is not None
            clauses = repository.list_clauses_by_document(task.document_id)
            matched = [clause for clause in clauses if "内窥镜主机须支持高清成像。" in clause.clause_text]

            self.assertEqual(len(matched), 1)

    def test_parse_worker_splits_long_clause_into_reviewable_slices(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            upload_service = UploadService(repository)
            upload_response = upload_service.create_review_task(
                UploadFile(
                    filename="招标文件.docx",
                    content=build_minimal_docx(
                        [
                            "第一章 评分办法",
                            "1.1 评分标准",
                            "（一）评分内容：投标人具有 ISO9001 质量管理体系认证证书。|（二）评分内容：投标人具有 ISO14001 环境管理体系认证证书。|（三）评分内容：投标人具有 ISO45001 职业健康安全管理体系认证证书。|（四）评分内容：投标人须提供具有 CMA 标识的检测报告。|（五）评分依据：以上资料均要求提供扫描件。",
                        ]
                    ),
                )
            )

            ParseWorker(repository).run_pending_jobs()

            task = repository.get_task(upload_response["task_id"])
            assert task is not None
            clauses = repository.list_clauses_by_document(task.document_id)
            score_clauses = [clause for clause in clauses if clause.location_label.startswith("第一章 评分办法 / 1.1 评分标准")]

            self.assertGreaterEqual(len(score_clauses), 2)
            self.assertTrue(any("片段2" in clause.location_label for clause in score_clauses))
            self.assertTrue(all(len(clause.location_label) < 80 for clause in score_clauses))
            parent_unit_ids = {
                clause.parent_unit_id
                for clause in score_clauses
                if clause.parent_unit_id is not None
            }
            self.assertEqual(len(parent_unit_ids), 1)

    def test_parse_worker_classifies_deviation_rows_as_deviation_units(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            upload_service = UploadService(repository)
            upload_response = upload_service.create_review_task(
                UploadFile(
                    filename="招标文件.docx",
                    content=build_docx_with_table(
                        ["第三章 采购需求偏离表", "3.1 技术偏离响应"],
                        [["条款号", "参数要求", "响应情况"], ["1", "支持双机热备", "负偏离"]],
                    ),
                )
            )

            ParseWorker(repository).run_pending_jobs()

            task = repository.get_task(upload_response["task_id"])
            assert task is not None
            clauses = repository.list_clauses_by_document(task.document_id)

            self.assertTrue(any(clause.unit_type == "偏离项" for clause in clauses))
            self.assertTrue(any(clause.module_type == "采购需求" for clause in clauses))

    def test_parse_worker_builds_stable_business_unit_entries_for_priority_modules(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            upload_service = UploadService(repository)
            upload_response = upload_service.create_review_task(
                UploadFile(
                    filename="招标文件.docx",
                    content=build_minimal_docx(
                        [
                            "第一章 资格条件",
                            "1.1 业绩要求",
                            "供应商近三年应具有同类项目业绩。",
                            "第二章 采购需求",
                            "2.1 交付要求",
                            "供应商应在合同签订后 7 天内交付。",
                            "第三章 评分办法",
                            "3.1 商务评分",
                            "商务分：根据类似项目业绩进行评分。",
                            "第四章 合同条款",
                            "4.1 付款方式",
                            "采购人在验收合格后 30 日内支付合同款。",
                        ]
                    ),
                )
            )

            ParseWorker(repository).run_pending_jobs()

            task = repository.get_task(upload_response["task_id"])
            assert task is not None
            clauses = repository.list_clauses_by_document(task.document_id)

            qualification_clause = next(clause for clause in clauses if clause.chapter_title == "第一章 资格条件")
            procurement_clause = next(clause for clause in clauses if clause.chapter_title == "第二章 采购需求")
            score_clause = next(clause for clause in clauses if clause.chapter_title == "第三章 评分办法")
            contract_clause = next(clause for clause in clauses if clause.chapter_title == "第四章 合同条款")

            self.assertEqual(qualification_clause.unit_label, "单条业绩要求")
            self.assertEqual(procurement_clause.unit_label, "单条交付要求")
            self.assertEqual(score_clause.unit_label, "商务分规则")
            self.assertEqual(contract_clause.unit_label, "付款条款")
            self.assertTrue(qualification_clause.review_unit_id.startswith("unit_"))
            self.assertTrue(all(clause.unit_name for clause in [qualification_clause, procurement_clause, score_clause, contract_clause]))

    def test_parse_worker_extracts_parameter_row_unit_name_from_table(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            upload_service = UploadService(repository)
            upload_response = upload_service.create_review_task(
                UploadFile(
                    filename="招标文件.docx",
                    content=build_docx_with_table(
                        ["第一章 采购需求", "1.1 参数表"],
                        [["参数名称", "指标要求"], ["图像分辨率", "支持 4K 输出"]],
                    ),
                )
            )

            ParseWorker(repository).run_pending_jobs()

            task = repository.get_task(upload_response["task_id"])
            assert task is not None
            clauses = repository.list_clauses_by_document(task.document_id)
            parameter_clause = next(
                clause
                for clause in clauses
                if clause.unit_label == "单个参数项" and "4K 输出" in clause.clause_text
            )

            self.assertEqual(parameter_clause.unit_name, "图像分辨率")

    def test_parse_worker_classifies_qualification_review_table(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            upload_service = UploadService(repository)
            upload_response = upload_service.create_review_task(
                UploadFile(
                    filename="招标文件.docx",
                    content=build_docx_with_table(
                        ["招标文件信息", "资格性审查表", "以下内容用于资格审查。"],
                        [["序号", "内容"], ["1", "投标人不符合资格要求，或未提交资格证明资料"]],
                    ),
                )
            )

            ParseWorker(repository).run_pending_jobs()

            task = repository.get_task(upload_response["task_id"])
            assert task is not None
            clauses = repository.list_clauses_by_document(task.document_id)
            self.assertTrue(any(clause.unit_label == "资格性审查表" for clause in clauses))

    def test_parse_worker_classifies_conformity_review_table(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            upload_service = UploadService(repository)
            upload_response = upload_service.create_review_task(
                UploadFile(
                    filename="招标文件.docx",
                    content=build_docx_with_table(
                        ["招标文件信息", "符合性审查表", "以下内容用于符合性审查。"],
                        [["序号", "内容"], ["1", "未按招标文件要求对实质性条款作出响应"]],
                    ),
                )
            )

            ParseWorker(repository).run_pending_jobs()

            task = repository.get_task(upload_response["task_id"])
            assert task is not None
            clauses = repository.list_clauses_by_document(task.document_id)
            self.assertTrue(any(clause.unit_label == "符合性审查表" for clause in clauses))

    def test_parse_worker_classifies_business_requirement_item(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            upload_service = UploadService(repository)
            upload_response = upload_service.create_review_task(
                UploadFile(
                    filename="招标文件.docx",
                    content=build_minimal_docx(
                        [
                            "第五章 商务要求",
                            "1.1 免费保修期外售后服务要求",
                            "投标人应按商务要求提供上门维护服务。",
                        ]
                    ),
                )
            )

            ParseWorker(repository).run_pending_jobs()

            task = repository.get_task(upload_response["task_id"])
            assert task is not None
            clauses = repository.list_clauses_by_document(task.document_id)
            self.assertTrue(any(clause.unit_label == "商务要求项" for clause in clauses))

    def test_parse_worker_classifies_policy_clause(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            upload_service = UploadService(repository)
            upload_response = upload_service.create_review_task(
                UploadFile(
                    filename="招标文件.docx",
                    content=build_minimal_docx(
                        [
                            "第六章 政策适用",
                            "1.1 中小企业政策",
                            "本项目执行中小企业价格扣除政策。",
                        ]
                    ),
                )
            )

            ParseWorker(repository).run_pending_jobs()

            task = repository.get_task(upload_response["task_id"])
            assert task is not None
            clauses = repository.list_clauses_by_document(task.document_id)
            self.assertTrue(any(clause.unit_label == "政策适用条款" for clause in clauses))

    def test_parse_worker_marks_default_chapter_content_as_uncertain_review_object(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            upload_service = UploadService(repository)
            upload_response = upload_service.create_review_task(
                UploadFile(
                    filename="招标文件.docx",
                    content=build_minimal_docx(
                        [
                            "特别警示条款",
                            "供应商参与投标不得存在下列情形。",
                            "1 | 与其他投标供应商存在关联关系。",
                        ]
                    ),
                )
            )

            ParseWorker(repository).run_pending_jobs()

            task = repository.get_task(upload_response["task_id"])
            assert task is not None
            clauses = repository.list_clauses_by_document(task.document_id)
            self.assertTrue(any(clause.unit_label == "不确定审查对象" for clause in clauses))

    def test_review_input_assembler_keeps_clause_type_and_chapter_context(self):
        root_dir = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            upload_service = UploadService(repository)
            upload_response = upload_service.create_review_task(
                UploadFile(
                    filename="招标文件.docx",
                    content=build_minimal_docx(
                        [
                            "第一章 资格要求",
                            "本章适用于供应商资格初审。",
                            "1.1 供应商资格",
                            "供应商须具备独立承担民事责任的能力。",
                        ]
                    ),
                )
            )
            ParseWorker(repository).run_pending_jobs()

            runtime_input = ReviewInputAssembler(repository, ReviewAssetLoader(root_dir)).assemble(
                upload_response["task_id"]
            )

            self.assertTrue(any(clause.chapter_title == "第一章 资格要求" for clause in runtime_input.clauses))
            self.assertTrue(any(clause.clause_type == "条款片段" for clause in runtime_input.clauses))
            self.assertTrue(any(clause.clause_type == "段落片段" for clause in runtime_input.clauses))
            self.assertIn("module_type", runtime_input.output_schema["risk_item_fields"])
            self.assertIn("unit_type", runtime_input.output_schema["risk_item_fields"])
            self.assertIn("unit_label", runtime_input.output_schema["risk_item_fields"])
            self.assertIn("unit_name", runtime_input.output_schema["risk_item_fields"])
            self.assertIn("review_unit_id", runtime_input.output_schema["risk_item_fields"])
            self.assertTrue(any(clause.module_type == "资格条件" for clause in runtime_input.clauses))

    def test_parse_worker_extracts_text_from_doc(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            upload_service = UploadService(repository)
            upload_response = upload_service.create_review_task(
                UploadFile(
                    filename="招标文件.doc",
                    content=(
                        "第一章 采购需求\n"
                        "1.1 项目背景\n"
                        "项目需要稳定的供货能力。\n"
                        "第二章 合同条款\n"
                        "2.1 履约要求\n"
                        "供应商应按期交付。"
                    ).encode("gb18030"),
                )
            )

            ParseWorker(repository).run_pending_jobs()

            task = repository.get_task(upload_response["task_id"])
            self.assertIsNotNone(task)
            self.assertEqual(task.internal_status, "review_queued")
            document = repository.get_document(task.document_id)
            self.assertIsNotNone(document)
            assert document is not None
            self.assertIn("项目需要稳定的供货能力", document.raw_text)

    def test_parse_worker_marks_task_failed_when_no_reviewable_text(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            upload_service = UploadService(repository)
            upload_response = upload_service.create_review_task(
                UploadFile(
                    filename="招标文件.pdf",
                    content=build_minimal_pdf(["1", "2", "3"]),
                )
            )

            ParseWorker(repository).run_pending_jobs()

            task = repository.get_task(upload_response["task_id"])
            self.assertIsNotNone(task)
            assert task is not None
            self.assertEqual(task.internal_status, "failed")
            self.assertEqual(task.error_code, "DOCUMENT_NO_REVIEWABLE_TEXT")
            self.assertIn("文件无可审查正文", task.status_message)

    def test_parse_worker_marks_task_failed_when_only_section_titles_exist(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            upload_service = UploadService(repository)
            upload_response = upload_service.create_review_task(
                UploadFile(
                    filename="招标文件.docx",
                    content=build_minimal_docx(
                        [
                            "第一章 总则和说明信息",
                            "第二章 评分办法和审查说明",
                            "第三章 合同条款和履约安排",
                        ]
                    ),
                )
            )

            ParseWorker(repository).run_pending_jobs()

            task = repository.get_task(upload_response["task_id"])
            self.assertIsNotNone(task)
            assert task is not None
            self.assertEqual(task.internal_status, "failed")
            self.assertEqual(task.error_code, "DOCUMENT_NO_REVIEWABLE_TEXT")
            self.assertIn("文件无可审查正文", task.status_message)
            self.assertEqual(list((Path(runtime_dir) / "queues" / "review").glob("*.json")), [])

    def test_asset_loader_loads_rule_pack_and_prompt(self):
        loader = ReviewAssetLoader(Path(__file__).resolve().parent.parent)
        rules = loader.load_rule_pack()
        prompt = loader.load_prompt_asset()

        self.assertEqual(len(rules), 12)
        self.assertEqual(rules[0]["rule_code"], "R1")
        self.assertIn("hit_definition", rules[0])
        self.assertIn("positive_examples", rules[0])
        self.assertEqual(prompt.version, "v1")
        self.assertIn("政府采购招标文件合规审查智能体", prompt.content_text)
        self.assertIn("优先关注高价值风险规则", prompt.content_text)

    def test_build_batch_payload_keeps_rule_guidance_fields(self):
        class RuntimeInputStub:
            rules = [
                {
                    "rule_code": "R5",
                    "rule_name": "品牌/型号指向检查",
                    "risk_level": "高",
                    "rule_domain": "公平竞争规则",
                    "execution_level": "自动判定",
                    "priority_hint": "高价值规则",
                    "hit_definition": "直接要求同品牌或原厂时命中。",
                    "positive_examples": ["提供同品牌主机。", "指定型号。", "超出条数的示例。"],
                    "negative_examples": ["说明可显示型号信息。"],
                    "focus_terms": ["同品牌", "原厂", "型号", "专利", "配套", "兼容", "额外术语"],
                }
            ]

        payload = _build_batch_payload(
            runtime_input=RuntimeInputStub(),
            clause_batch=[
                build_clause_record(
                    clause_id="clause_demo",
                    document_id="document_demo",
                    chapter_id="chapter_demo",
                    chapter_title="第四章 技术要求",
                    clause_order=1,
                    clause_text="提供与影像处理平台同品牌内窥镜主机。",
                    location_label="第四章 技术要求 / 1.5.2 内窥镜控制单元",
                    clause_type="条款片段",
                )
            ],
            clause_max_chars=200,
            rule_limit=6,
            rule_candidate_map={"R5": []},
        )

        self.assertEqual(payload["rules"][0]["rule_code"], "R5")
        self.assertIn("hit_definition", payload["rules"][0])
        self.assertIn("positive_examples", payload["rules"][0])
        self.assertNotIn("negative_examples", payload["rules"][0])
        self.assertEqual(len(payload["rules"][0]["positive_examples"]), 2)
        self.assertEqual(len(payload["rules"][0]["focus_terms"]), 6)
        self.assertNotIn("task", payload)
        self.assertNotIn("location_label", payload["clauses"][0])
        self.assertIn("review_unit_id", payload["clauses"][0])
        self.assertIn("unit_label", payload["clauses"][0])
        self.assertIn("unit_name", payload["clauses"][0])
        self.assertIn("优先检查 R1、R3、R5、R9、R12", payload["review_requirements"][1])

    def test_classify_clause_business_modules_uses_business_keywords(self):
        clause = build_clause_record(
            clause_id="clause_module",
            document_id="document_demo",
            chapter_id="chapter_demo",
            chapter_title="第二章 评分办法",
            clause_order=1,
            clause_text="采用综合评价并可酌情打分。",
            location_label="第二章 评分办法 / 2.1",
            clause_type="条款片段",
        )

        modules = _classify_clause_business_modules(clause)

        self.assertIn("评分办法", modules)

    def test_select_rules_for_clause_batch_prefers_matched_and_high_priority_rules(self):
        rules = [
            {
                "rule_code": "R1",
                "rule_name": "地域限制检查",
                "risk_level": "高",
                "execution_level": "自动判定",
                "priority_hint": "高价值",
                "hit_definition": "出现本地注册、本地办公时命中。",
                "focus_terms": ["本地注册", "本地办公"],
                "positive_examples": ["供应商须本地注册并在本地办公。"],
            },
            {
                "rule_code": "R4",
                "rule_name": "售后服务检查",
                "risk_level": "中",
                "execution_level": "辅助提示",
                "priority_hint": "",
                "hit_definition": "出现驻场服务要求时命中。",
                "focus_terms": ["驻场服务"],
                "positive_examples": ["供应商须提供驻场服务。"],
            },
            {
                "rule_code": "R5",
                "rule_name": "品牌型号指向检查",
                "risk_level": "高",
                "execution_level": "自动判定",
                "priority_hint": "高价值",
                "hit_definition": "出现品牌型号限制时命中。",
                "focus_terms": ["品牌", "型号"],
                "positive_examples": ["提供同品牌主机。"],
            },
            {
                "rule_code": "R8",
                "rule_name": "交付周期检查",
                "risk_level": "低",
                "execution_level": "辅助提示",
                "priority_hint": "",
                "hit_definition": "出现极短交付期时命中。",
                "focus_terms": ["交付期"],
                "positive_examples": ["7 天内交付。"],
            },
            {
                "rule_code": "R9",
                "rule_name": "评分项未量化检查",
                "risk_level": "高",
                "execution_level": "自动判定",
                "priority_hint": "高价值",
                "hit_definition": "出现综合评价、酌情打分时命中。",
                "focus_terms": ["综合评价", "酌情打分"],
                "positive_examples": ["采用综合评价并可酌情打分。"],
            },
            {
                "rule_code": "R12",
                "rule_name": "证书资质检查",
                "risk_level": "高",
                "execution_level": "自动判定",
                "priority_hint": "高价值",
                "hit_definition": "出现执业医师证等资质要求时命中。",
                "focus_terms": ["执业医师证"],
                "positive_examples": ["团队成员须具备执业医师证。"],
            },
            {
                "rule_code": "R2",
                "rule_name": "一般规则",
                "risk_level": "中",
                "execution_level": "辅助提示",
                "priority_hint": "",
                "hit_definition": "一般检查。",
                "focus_terms": ["一般表述"],
                "positive_examples": ["一般表述。"],
            },
        ]
        clause_batch = [
            build_clause_record(
                clause_id="clause_demo",
                document_id="document_demo",
                chapter_id="chapter_demo",
                chapter_title="第一章 资格要求",
                clause_order=1,
                clause_text="供应商须本地注册并在本地办公，且采用综合评价并可酌情打分。",
                location_label="第一章 资格要求 / 1.1",
                clause_type="条款片段",
            )
        ]

        selected = _select_rules_for_clause_batch(
            rules=rules,
            clause_batch=clause_batch,
            rule_limit=6,
            rule_candidate_map={
                "R1": clause_batch,
                "R4": clause_batch,
                "R5": clause_batch,
                "R8": [],
                "R9": clause_batch,
                "R12": [],
                "R2": [],
            },
        )

        self.assertEqual(len(selected), 4)
        self.assertIn("R1", [rule["rule_code"] for rule in selected])
        self.assertIn("R9", [rule["rule_code"] for rule in selected])
        self.assertIn("R5", [rule["rule_code"] for rule in selected])
        self.assertIn("R4", [rule["rule_code"] for rule in selected])

    def test_select_rule_candidate_clause_map_prefers_business_modules(self):
        rules = [
            {
                "rule_code": "R3",
                "rule_name": "资格条件过高检查",
                "rule_domain": "合法性规则",
                "hit_definition": "增设与项目无关资质时命中。",
                "focus_terms": ["资质", "证书"],
                "positive_examples": ["要求提供额外资质证书。"],
            },
            {
                "rule_code": "R9",
                "rule_name": "评分项未量化检查",
                "rule_domain": "评审可解释性规则",
                "hit_definition": "综合评价、酌情打分时命中。",
                "focus_terms": ["综合评价", "酌情打分"],
                "positive_examples": ["采用综合评价并可酌情打分。"],
            },
        ]
        clauses = [
            build_clause_record(
                clause_id="c1",
                document_id="d1",
                chapter_id="ch1",
                chapter_title="第一章 资格条件",
                clause_order=1,
                clause_text="要求提供额外资质证书。",
                location_label="第一章 资格条件 / 1.1",
                clause_type="条款片段",
            ),
            build_clause_record(
                clause_id="c2",
                document_id="d1",
                chapter_id="ch2",
                chapter_title="第二章 评分办法",
                clause_order=2,
                clause_text="采用综合评价并可酌情打分。",
                location_label="第二章 评分办法 / 2.1",
                clause_type="条款片段",
            ),
            build_clause_record(
                clause_id="c3",
                document_id="d1",
                chapter_id="ch3",
                chapter_title="第三章 其他说明",
                clause_order=3,
                clause_text="一般说明。",
                location_label="第三章 其他说明 / 3.1",
                clause_type="段落片段",
            ),
        ]

        mapping = _select_rule_candidate_clause_map(
            rules=rules,
            clauses=clauses,
            max_clauses_per_rule=2,
        )

        self.assertEqual([clause.clause_id for clause in mapping["R3"]], ["c1"])
        self.assertEqual([clause.clause_id for clause in mapping["R9"]], ["c2"])

    def test_select_rule_candidate_clause_map_prefers_specific_review_units(self):
        rules = [
            {
                "rule_code": "R9",
                "rule_name": "评分项未量化检查",
                "rule_domain": "评审可解释性规则",
                "hit_definition": "综合评价、酌情打分时命中。",
                "focus_terms": ["综合评价", "酌情打分"],
                "positive_examples": ["根据方案优良中差酌情打分。"],
            },
            {
                "rule_code": "R12",
                "rule_name": "关键条款缺失/责任失衡检查",
                "rule_domain": "合同与程序风险规则",
                "hit_definition": "责任失衡或关键条款缺失时命中。",
                "focus_terms": ["第三方检测费用", "全部由中标人承担"],
                "positive_examples": ["检测费用全部由中标人承担。"],
            },
        ]
        clauses = [
            build_clause_record(
                clause_id="score_generic",
                document_id="d1",
                chapter_id="ch1",
                chapter_title="第二章 评分办法",
                clause_order=1,
                clause_text="本项目采用综合评分法。",
                location_label="第二章 评分办法 / 2.1",
                module_type="评分办法",
                unit_type="条款",
                unit_label="普通条款",
                unit_name="评审方法",
                clause_type="条款片段",
            ),
            build_clause_record(
                clause_id="score_item",
                document_id="d1",
                chapter_id="ch1",
                chapter_title="第二章 评分办法",
                clause_order=2,
                clause_text="根据培训方案优良中差酌情打分。",
                location_label="第二章 评分办法 / 2.2",
                module_type="评分办法",
                unit_type="评分项",
                unit_label="单个评分项",
                unit_name="培训方案评分",
                clause_type="条款片段",
            ),
            build_clause_record(
                clause_id="contract_generic",
                document_id="d1",
                chapter_id="ch2",
                chapter_title="第五章 合同条款",
                clause_order=3,
                clause_text="合同其他事项说明。",
                location_label="第五章 合同条款 / 5.1",
                module_type="合同条款",
                unit_type="合同项",
                unit_label="单条合同条款",
                unit_name="其他事项",
                clause_type="条款片段",
            ),
            build_clause_record(
                clause_id="expense_clause",
                document_id="d1",
                chapter_id="ch2",
                chapter_title="第五章 合同条款",
                clause_order=4,
                clause_text="第三方检测费用全部由中标人承担，无论结果是否合格。",
                location_label="第五章 合同条款 / 5.2",
                module_type="合同条款",
                unit_type="合同项",
                unit_label="费用承担条款",
                unit_name="检测费用承担",
                clause_type="条款片段",
            ),
        ]

        mapping = _select_rule_candidate_clause_map(
            rules=rules,
            clauses=clauses,
            max_clauses_per_rule=2,
        )

        self.assertEqual([clause.clause_id for clause in mapping["R9"][:2]], ["score_item", "score_generic"])
        self.assertEqual([clause.clause_id for clause in mapping["R12"][:2]], ["expense_clause", "contract_generic"])

    def test_select_candidate_clauses_prefers_high_value_sections_and_matches(self):
        rules = [
            {
                "rule_code": "R1",
                "rule_name": "地域限制检查",
                "hit_definition": "出现本地注册、本地办公时命中。",
                "focus_terms": ["本地注册", "本地办公"],
                "positive_examples": ["供应商须本地注册并在本地办公。"],
            },
            {
                "rule_code": "R9",
                "rule_name": "评分项未量化检查",
                "hit_definition": "出现综合评价、酌情打分时命中。",
                "focus_terms": ["综合评价", "酌情打分"],
                "positive_examples": ["采用综合评价并可酌情打分。"],
            },
        ]
        clauses = [
            build_clause_record(
                clause_id="c1",
                document_id="d1",
                chapter_id="ch1",
                chapter_title="第一章 总则",
                clause_order=1,
                clause_text="项目概况说明。",
                location_label="第一章 总则 / 1.1",
                clause_type="段落片段",
            ),
            build_clause_record(
                clause_id="c2",
                document_id="d1",
                chapter_id="ch2",
                chapter_title="第二章 资格要求",
                clause_order=2,
                clause_text="供应商须本地注册并在本地办公。",
                location_label="第二章 资格要求 / 2.1",
                clause_type="条款片段",
            ),
            build_clause_record(
                clause_id="c3",
                document_id="d1",
                chapter_id="ch3",
                chapter_title="第三章 评分办法",
                clause_order=3,
                clause_text="采用综合评价并可酌情打分。",
                location_label="第三章 评分办法 / 3.1",
                clause_type="条款片段",
            ),
            build_clause_record(
                clause_id="c4",
                document_id="d1",
                chapter_id="ch4",
                chapter_title="第四章 其他说明",
                clause_order=4,
                clause_text="一般说明文字。",
                location_label="第四章 其他说明 / 4.1",
                clause_type="段落片段",
            ),
        ]

        rule_candidate_map = _select_rule_candidate_clause_map(
            rules=rules,
            clauses=clauses,
            max_clauses_per_rule=2,
        )

        selected = _select_candidate_clauses(
            clauses=clauses,
            rules=rules,
            rule_candidate_map=rule_candidate_map,
            max_clauses=2,
        )

        self.assertEqual([clause.clause_id for clause in selected], ["c2", "c3"])

    def test_review_input_assembler_builds_runtime_input(self):
        root_dir = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            upload_service = UploadService(repository)
            upload_response = upload_service.create_review_task(
                UploadFile(
                    filename="招标文件.docx",
                    content=build_minimal_docx(
                        [
                            "第一章 总则",
                            "1.1 项目概况",
                            "供应商须本地注册。",
                            "第二章 评分办法",
                            "2.1 评分标准",
                            "综合评价。",
                        ]
                    ),
                )
            )
            ParseWorker(repository).run_pending_jobs()

            runtime_input = ReviewInputAssembler(repository, ReviewAssetLoader(root_dir)).assemble(
                upload_response["task_id"]
            )

            self.assertEqual(runtime_input.task_id, upload_response["task_id"])
            self.assertEqual(runtime_input.file_name, "招标文件.docx")
            self.assertEqual(len(runtime_input.rules), 12)
            self.assertGreaterEqual(len(runtime_input.clauses), 2)
            self.assertIn("risk_item_fields", runtime_input.output_schema)
            self.assertIn("chapter_title", runtime_input.output_schema["risk_item_fields"])
            self.assertIn("clause_type", runtime_input.output_schema["risk_item_fields"])
            self.assertIn("chapter_title", runtime_input.output_schema["evidence_item_fields"])
            self.assertIn("clause_type", runtime_input.output_schema["evidence_item_fields"])
            self.assertIn("政府采购招标文件合规审查智能体", runtime_input.prompt_text)

    def test_review_executor_consumes_review_queue_and_persists_intermediate_objects(self):
        root_dir = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as runtime_dir, fake_llm_environment():
            repository = JsonRepository(Path(runtime_dir))
            upload_service = UploadService(repository)
            upload_response = upload_service.create_review_task(
                UploadFile(
                    filename="招标文件.docx",
                    content=build_minimal_docx(
                        [
                            "第一章 资格要求",
                            "1.1 供应商资格",
                            "供应商须本地注册并在本地办公。",
                            "第二章 评分办法",
                            "2.1 评分标准",
                            "采用综合评价并可酌情打分。",
                        ]
                    ),
                )
            )
            ParseWorker(repository).run_pending_jobs()

            processed_count = ReviewExecutor(repository, root_dir).run_pending_jobs()

            self.assertEqual(processed_count, 1)
            task = repository.get_task(upload_response["task_id"])
            self.assertIsNotNone(task)
            self.assertEqual(task.internal_status, "aggregating")
            self.assertIn("中间审查结果", task.status_message)

            risks = repository.list_risks_by_task(upload_response["task_id"])
            self.assertGreaterEqual(len(risks), 2)
            self.assertIn(risks[0].rule_id, {"rule_v1_r1", "rule_v1_r9"})
            self.assertIn("LLM", risks[0].review_reasoning)
            self.assertIn("片段", risks[0].review_reasoning)
            evidences = repository.list_evidences_by_risk(risks[0].risk_id)
            self.assertEqual(len(evidences), 1)
            self.assertTrue(evidences[0].quoted_text)
            self.assertIn("原文证据", evidences[0].evidence_note)
            self.assertIn("片段", evidences[0].evidence_note)
            self.assertEqual(list((Path(runtime_dir) / "queues" / "review").glob("*.json")), [])
            self.assertEqual(len(list((Path(runtime_dir) / "queues" / "result").glob("*.json"))), 1)

    def test_chunk_clauses_for_review_respects_count_and_char_budget(self):
        class ClauseStub:
            def __init__(self, clause_text: str):
                self.clause_text = clause_text

        clauses = [
            ClauseStub("a" * 320),
            ClauseStub("b" * 310),
            ClauseStub("c" * 280),
            ClauseStub("d" * 200),
        ]

        chunks = _chunk_clauses_for_review(
            clauses,
            batch_size=4,
            clause_max_chars=400,
            batch_char_budget=700,
        )

        self.assertEqual([len(chunk) for chunk in chunks], [2, 2])

    def test_next_retry_clause_max_chars_has_floor(self):
        self.assertEqual(_next_retry_clause_max_chars(900), 450)
        self.assertEqual(_next_retry_clause_max_chars(450), 300)
        self.assertEqual(_next_retry_clause_max_chars(300), 300)

    def test_normalize_finding_rule_code_remaps_scoring_semantics_from_r12_to_r9(self):
        clause = build_clause_record(
            clause_id="score_clause",
            document_id="d1",
            chapter_id="ch1",
            chapter_title="第四章 评分办法",
            clause_order=1,
            clause_text="①评审为优（方案内容全面、清晰、针对性强、可操作性强）的，最高得40分。",
            location_label="第四章 评分办法 / 4.1",
            module_type="评分办法",
            unit_type="评分项",
            unit_label="单个评分项",
            unit_name="售后服务及培训方案评价",
            clause_type="条款片段",
        )

        normalized = _normalize_finding_rule_code(
            finding={
                "rule_code": "R12",
                "risk_title": "评分标准量化不足，存在主观裁量空间",
                "review_reasoning": "采用优良中差式打分，评审尺度不够量化。",
                "evidence_text": "①评审为优（方案内容全面、清晰、针对性强、可操作性强）的，最高得40分。",
            },
            clause=clause,
            available_rule_codes={"R9", "R12"},
        )

        self.assertEqual(normalized, "R9")

    def test_normalize_finding_rule_code_keeps_contract_semantics_on_r12(self):
        clause = build_clause_record(
            clause_id="contract_clause",
            document_id="d1",
            chapter_id="ch2",
            chapter_title="第五章 合同条款",
            clause_order=2,
            clause_text="终验合格后支付至合同金额的95%，剩余款项待财政资金下达后支付。",
            location_label="第五章 合同条款 / 5.2",
            module_type="合同条款",
            unit_type="合同项",
            unit_label="付款条款",
            unit_name="付款安排",
            clause_type="条款片段",
        )

        normalized = _normalize_finding_rule_code(
            finding={
                "rule_code": "R12",
                "risk_title": "付款节点与财政资金下达挂钩，合同责任分配失衡",
                "review_reasoning": "付款条件受采购人内部资金到位影响，供应商回款风险偏高。",
                "evidence_text": "剩余款项待财政资金下达后支付。",
            },
            clause=clause,
            available_rule_codes={"R9", "R12"},
        )

        self.assertEqual(normalized, "R12")

    def test_normalize_finding_rule_code_remaps_scoring_keywords_even_for_generic_unit(self):
        clause = build_clause_record(
            clause_id="generic_score_clause",
            document_id="d1",
            chapter_id="ch3",
            chapter_title="第五章 其他要求",
            clause_order=3,
            clause_text="①评审为优的最高得40分；②评审为良的最高得20分；③评审为中的最高得10分。",
            location_label="第五章 其他要求 / 售后服务及培训方案评价",
            module_type="其他",
            unit_type="条款",
            unit_label="不确定审查对象",
            unit_name="售后服务及培训方案评价",
            clause_type="条款片段",
        )

        normalized = _normalize_finding_rule_code(
            finding={
                "rule_code": "R12",
                "risk_title": "评分标准量化不足，存在自由裁量权过大风险",
                "review_reasoning": "采用优良中差式评审，评分标准不够客观量化。",
                "evidence_text": "①评审为优的最高得40分；②评审为良的最高得20分；③评审为中的最高得10分。",
            },
            clause=clause,
            available_rule_codes={"R1", "R9", "R12"},
        )

        self.assertEqual(normalized, "R9")

    def test_review_executor_splits_failed_batch_and_keeps_task_running(self):
        class FlakyClient:
            max_clauses = 10
            max_clauses_per_rule = 10
            batch_size = 4
            clause_max_chars = 800
            batch_char_budget = 1000

            def review_batch(self, *, prompt_text: str, payload: dict[str, object]) -> list[dict[str, object]]:
                clauses = payload["clauses"]
                assert isinstance(clauses, list)
                if len(clauses) > 1:
                    raise LlmRequestError("mock 504")
                clause = clauses[0]
                assert isinstance(clause, dict)
                return [
                    {
                        "clause_id": clause["clause_id"],
                        "rule_code": "R1",
                        "risk_title": "地域限制条款",
                        "risk_level": "高",
                        "risk_category": "公平竞争",
                        "evidence_text": str(clause["clause_text"]),
                        "review_reasoning": "模拟拆批后成功。",
                        "need_human_confirm": False,
                    }
                ]

        root_dir = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as runtime_dir, fake_llm_environment():
            repository = JsonRepository(Path(runtime_dir))
            upload_service = UploadService(repository)
            upload_response = upload_service.create_review_task(
                UploadFile(
                    filename="招标文件.docx",
                    content=build_minimal_docx(
                        [
                            "第一章 资格要求",
                            "1.1 供应商资格",
                            "供应商须本地注册并在本地办公。",
                            "1.2 服务要求",
                            "供应商须提供本地常驻服务团队。",
                            "第二章 评分办法",
                            "2.1 评分标准",
                            "采用综合评价并可酌情打分。",
                        ]
                    ),
                )
            )
            ParseWorker(repository).run_pending_jobs()

            executor = ReviewExecutor(repository, root_dir)
            executor.client = FlakyClient()

            processed_count = executor.run_pending_jobs()

            self.assertEqual(processed_count, 1)
            task = repository.get_task(upload_response["task_id"])
            self.assertIsNotNone(task)
            assert task is not None
            self.assertEqual(task.internal_status, "aggregating")
            risks = repository.list_risks_by_task(upload_response["task_id"])
            self.assertGreaterEqual(len(risks), 2)

    def test_result_aggregator_generates_result_and_marks_task_completed(self):
        root_dir = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as runtime_dir, fake_llm_environment():
            repository = JsonRepository(Path(runtime_dir))
            upload_service = UploadService(repository)
            upload_response = upload_service.create_review_task(
                UploadFile(
                    filename="招标文件.docx",
                    content=build_minimal_docx(
                        [
                            "第一章 资格要求",
                            "1.1 供应商资格",
                            "供应商须本地注册并在本地办公。",
                            "第二章 评分办法",
                            "2.1 评分标准",
                            "采用综合评价并可酌情打分。",
                        ]
                    ),
                )
            )
            ParseWorker(repository).run_pending_jobs()
            ReviewExecutor(repository, root_dir).run_pending_jobs()

            processed_count = ResultAggregator(repository, root_dir).run_pending_jobs()

            self.assertEqual(processed_count, 1)
            task = repository.get_task(upload_response["task_id"])
            self.assertIsNotNone(task)
            self.assertEqual(task.internal_status, "completed")
            self.assertEqual(task.status, "completed")
            self.assertIsNotNone(task.completed_at)

            result = repository.get_result_by_task(upload_response["task_id"])
            self.assertIsNotNone(result)
            assert result is not None
            self.assertEqual(result.status, "completed")
            self.assertIn("高风险问题", result.overall_conclusion)
            self.assertIn("# 审查报告", result.report_markdown)
            self.assertIn("# 最终结论", result.conclusion_markdown)
            self.assertIn("- 章节上下文：第一章 资格要求", result.report_markdown)
            self.assertIn("- 片段类型：条款片段", result.report_markdown)
            self.assertIn("风险组", result.report_markdown)
            self.assertIn("高风险组数量", result.conclusion_markdown)
            self.assertTrue(Path(result.report_file_path).exists())
            self.assertTrue(Path(result.conclusion_file_path).exists())
            self.assertEqual(list((Path(runtime_dir) / "queues" / "result").glob("*.json")), [])

    def test_worker_runner_processes_uploaded_task_to_completed(self):
        root_dir = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as runtime_dir, fake_llm_environment():
            repository = JsonRepository(Path(runtime_dir))
            upload_service = UploadService(repository)
            upload_response = upload_service.create_review_task(
                UploadFile(
                    filename="招标文件.pdf",
                    content=(
                        "第一章 资格要求\n"
                        "1.1 供应商资格\n"
                        "供应商须本地注册并在本地办公。\n"
                        "第二章 评分办法\n"
                        "2.1 评分标准\n"
                        "采用综合评价并可酌情打分。\n"
                    ).encode("utf-8"),
                )
            )

            result = WorkerRunner(repository, root_dir).run_until_idle()

            self.assertGreaterEqual(result["rounds"], 2)
            self.assertEqual(result["parse_jobs"], 1)
            self.assertEqual(result["review_jobs"], 1)
            self.assertEqual(result["result_jobs"], 1)

            task = repository.get_task(upload_response["task_id"])
            self.assertIsNotNone(task)
            self.assertEqual(task.internal_status, "completed")
            self.assertEqual(task.status, "completed")

            stored_result = repository.get_result_by_task(upload_response["task_id"])
            self.assertIsNotNone(stored_result)
            self.assertEqual(list((Path(runtime_dir) / "queues" / "parse").glob("*.json")), [])
            self.assertEqual(list((Path(runtime_dir) / "queues" / "review").glob("*.json")), [])
            self.assertEqual(list((Path(runtime_dir) / "queues" / "result").glob("*.json")), [])
