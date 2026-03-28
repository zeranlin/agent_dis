from __future__ import annotations

import json
import tempfile
import unittest
import zipfile
from io import BytesIO
from pathlib import Path

from app.asset_loader import ReviewAssetLoader
from app.parser_worker import ParseWorker
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


class ParseWorkerTestCase(unittest.TestCase):
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
            evidences = repository.list_evidences_by_risk(risks[0].risk_id)
            self.assertEqual(len(evidences), 1)
            self.assertTrue(evidences[0].quoted_text)
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
