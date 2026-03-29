from __future__ import annotations

import json
import multiprocessing
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

from app.asset_loader import ReviewAssetLoader
from app.models import build_clause_record, build_risk_item_record
from app.parser_worker import ParseWorker
from app.result_aggregator import build_report_markdown
from app.repository import JsonRepository
from app.result_aggregator import ResultAggregator
from app.review_assembler import ReviewInputAssembler
from app.review_executor import ReviewExecutor
from app.upload_service import UploadFile, UploadService
from app.worker_runner import WorkerRunner


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
        class EmptyEvidenceRepository:
            @staticmethod
            def list_evidences_by_risk(_risk_id: str) -> list[object]:
                return []

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

        markdown = build_report_markdown(
            file_name="招标文件.docx",
            overall_conclusion="测试结论",
            risks=[low_risk, high_risk],
            repository=EmptyEvidenceRepository(),
        )

        self.assertLess(markdown.index("高风险规则"), markdown.index("低风险规则"))
        self.assertIn("- 章节上下文：第一章 资格要求", markdown)
        self.assertIn("- 片段类型：条款片段", markdown)

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

            self.assertTrue(any("供应商须具备独立承担民事责任的能力。" in text for text in chapter_texts))
            self.assertTrue(any(location.startswith("第一章 资格要求 / 1.1 供应商资格") for location in clause_locations))
            self.assertIn("条款片段", clause_types)
            self.assertTrue(all(title == "第一章 资格要求" for title in clause_chapter_titles))

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
        self.assertEqual(prompt.version, "v1")
        self.assertIn("政府采购招标文件合规审查智能体", prompt.content_text)

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
            self.assertIn("第", risks[0].risk_description)
            self.assertIn("片段", risks[0].review_reasoning)
            evidences = repository.list_evidences_by_risk(risks[0].risk_id)
            self.assertEqual(len(evidences), 1)
            self.assertTrue(evidences[0].quoted_text)
            self.assertIn("原文包含关键词", evidences[0].evidence_note)
            self.assertIn("片段", evidences[0].evidence_note)
            self.assertEqual(list((Path(runtime_dir) / "queues" / "review").glob("*.json")), [])
            self.assertEqual(len(list((Path(runtime_dir) / "queues" / "result").glob("*.json"))), 1)

    def test_result_aggregator_generates_result_and_marks_task_completed(self):
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
            self.assertTrue(Path(result.report_file_path).exists())
            self.assertTrue(Path(result.conclusion_file_path).exists())
            self.assertEqual(list((Path(runtime_dir) / "queues" / "result").glob("*.json")), [])

    def test_worker_runner_processes_uploaded_task_to_completed(self):
        root_dir = Path(__file__).resolve().parent.parent
        with tempfile.TemporaryDirectory() as runtime_dir:
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
