from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from app.asset_loader import ReviewAssetLoader
from app.parser_worker import ParseWorker
from app.repository import JsonRepository
from app.upload_service import UploadFile, UploadService


class ParseWorkerTestCase(unittest.TestCase):
    def test_parse_worker_consumes_queue_and_marks_task_parsed(self):
        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = JsonRepository(Path(runtime_dir))
            upload_service = UploadService(repository)
            upload_response = upload_service.create_review_task(
                UploadFile(
                    filename="招标文件.docx",
                    content=(
                        "第一章 总则\n"
                        "1.1 项目概况\n"
                        "本项目用于测试。\n"
                        "第二章 评分办法\n"
                        "2.1 评分标准\n"
                        "综合评价。"
                    ).encode("utf-8"),
                )
            )

            processed_count = ParseWorker(repository).run_pending_jobs()

            self.assertEqual(processed_count, 1)
            task = repository.get_task(upload_response["task_id"])
            self.assertIsNotNone(task)
            self.assertEqual(task.internal_status, "parsed")
            document = repository.get_document(task.document_id)
            self.assertEqual(document.parsed_status, "parsed")

            chapters = json.loads((Path(runtime_dir) / "metadata" / "chapters.json").read_text(encoding="utf-8"))
            clauses = json.loads((Path(runtime_dir) / "metadata" / "clauses.json").read_text(encoding="utf-8"))
            self.assertGreaterEqual(len(chapters), 2)
            self.assertGreaterEqual(len(clauses), 2)
            self.assertEqual(list((Path(runtime_dir) / "queues" / "parse").glob("*.json")), [])

    def test_asset_loader_loads_rule_pack_and_prompt(self):
        loader = ReviewAssetLoader(Path(__file__).resolve().parent.parent)
        rules = loader.load_rule_pack()
        prompt = loader.load_prompt_asset()

        self.assertEqual(len(rules), 12)
        self.assertEqual(rules[0]["rule_code"], "R1")
        self.assertEqual(prompt.version, "v1")
        self.assertIn("政府采购招标文件合规审查智能体", prompt.content_text)
