from __future__ import annotations

import json
import threading
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

from app.repository import JsonRepository
from app.server import ReviewHTTPServer, create_service
from app.upload_service import ResultAccessError, UploadFile, UploadProcessingError, UploadService
from app.worker_runner import WorkerRunner


def build_multipart_body(boundary: str, filename: str, content: bytes) -> bytes:
    lines = [
        f"--{boundary}".encode("utf-8"),
        f'Content-Disposition: form-data; name="file"; filename="{filename}"'.encode("utf-8"),
        b"Content-Type: application/octet-stream",
        b"",
        content,
        f"--{boundary}--".encode("utf-8"),
        b"",
    ]
    return b"\r\n".join(lines)


class TestServerContext:
    def __init__(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.previous_runtime_dir = None
        self.server = None
        self.thread = None

    def __enter__(self):
        import os

        self.previous_runtime_dir = os.environ.get("AGENT_DIS_RUNTIME_DIR")
        os.environ["AGENT_DIS_RUNTIME_DIR"] = self.temp_dir.name
        service = create_service()
        self.server = ReviewHTTPServer(("127.0.0.1", 0), service)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        import os

        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        if self.previous_runtime_dir is None:
            os.environ.pop("AGENT_DIS_RUNTIME_DIR", None)
        else:
            os.environ["AGENT_DIS_RUNTIME_DIR"] = self.previous_runtime_dir
        self.temp_dir.cleanup()

    @property
    def base_url(self) -> str:
        host, port = self.server.server_address
        return f"http://{host}:{port}"

    @property
    def runtime_dir(self) -> Path:
        return Path(self.temp_dir.name)


class UploadApiTestCase(unittest.TestCase):
    def test_result_page_renders_completed_task(self):
        with TestServerContext() as server:
            boundary = f"boundary-{uuid4().hex}"
            body = build_multipart_body(
                boundary,
                "招标文件.docx",
                (
                    "第一章 资格要求\n"
                    "1.1 供应商资格\n"
                    "供应商须本地注册并在本地办公。\n"
                    "第二章 评分办法\n"
                    "2.1 评分标准\n"
                    "采用综合评价并可酌情打分。\n"
                ).encode("utf-8"),
            )
            request = urllib.request.Request(
                f"{server.base_url}/api/v1/review-tasks",
                data=body,
                method="POST",
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
            with urllib.request.urlopen(request) as response:
                payload = json.loads(response.read().decode("utf-8"))

            task_id = payload["task_id"]
            WorkerRunner(JsonRepository(server.runtime_dir), Path(__file__).resolve().parent.parent).run_until_idle()

            with urllib.request.urlopen(f"{server.base_url}/review-tasks/{task_id}/page") as response:
                html = response.read().decode("utf-8")
                headers = dict(response.headers.items())

            self.assertEqual(headers["Content-Type"], "text/html; charset=utf-8")
            self.assertIn("结果页最小实现", html)
            self.assertIn("结果已生成", html)
            self.assertIn("建议阅读顺序", html)
            self.assertIn("重点风险摘要", html)
            self.assertIn("快速操作", html)
            self.assertIn("查看建议", html)
            self.assertIn("刷新当前结果页", html)
            self.assertIn("/review-tasks/", html)
            self.assertIn("/api/v1/review-tasks/", html)
            self.assertIn("最终结论.md", html)
            self.assertIn("审查报告.md", html)

    def test_result_page_renders_reviewing_task_feedback(self):
        with TestServerContext() as server:
            boundary = f"boundary-{uuid4().hex}"
            body = build_multipart_body(boundary, "招标文件.pdf", b"fake-pdf-content")
            request = urllib.request.Request(
                f"{server.base_url}/api/v1/review-tasks",
                data=body,
                method="POST",
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
            with urllib.request.urlopen(request) as response:
                payload = json.loads(response.read().decode("utf-8"))

            with urllib.request.urlopen(f"{server.base_url}/review-tasks/{payload['task_id']}/page") as response:
                html = response.read().decode("utf-8")

            self.assertIn("审核中", html)
            self.assertIn("查看状态接口", html)
            self.assertIn("建议：先查看状态接口确认当前阶段", html)

    def test_get_result_and_download_files_after_worker_run(self):
        with TestServerContext() as server:
            boundary = f"boundary-{uuid4().hex}"
            body = build_multipart_body(
                boundary,
                "招标文件.docx",
                (
                    "第一章 资格要求\n"
                    "1.1 供应商资格\n"
                    "供应商须本地注册并在本地办公。\n"
                    "第二章 评分办法\n"
                    "2.1 评分标准\n"
                    "采用综合评价并可酌情打分。\n"
                ).encode("utf-8"),
            )
            request = urllib.request.Request(
                f"{server.base_url}/api/v1/review-tasks",
                data=body,
                method="POST",
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
            with urllib.request.urlopen(request) as response:
                payload = json.loads(response.read().decode("utf-8"))

            task_id = payload["task_id"]
            WorkerRunner(JsonRepository(server.runtime_dir), Path(__file__).resolve().parent.parent).run_until_idle()

            with urllib.request.urlopen(f"{server.base_url}/api/v1/review-tasks/{task_id}/result") as response:
                result_payload = json.loads(response.read().decode("utf-8"))

            self.assertEqual(result_payload["task_id"], task_id)
            self.assertEqual(result_payload["status"], "completed")
            self.assertEqual(len(result_payload["downloadable_files"]), 2)
            self.assertIn("审查已完成", result_payload["summary_title"])
            self.assertIn("conclusion_markdown", result_payload)
            self.assertIn("risk_count_summary", result_payload)
            self.assertIn("top_risks", result_payload)
            self.assertIn("generated_at", result_payload)
            self.assertEqual(result_payload["risk_count_summary"]["high"], 2)
            self.assertGreaterEqual(len(result_payload["top_risks"]), 1)
            self.assertIn("page_url", result_payload)
            self.assertIn("status_api_url", result_payload)
            self.assertIn("result_api_url", result_payload)

            with urllib.request.urlopen(f"{server.base_url}/api/v1/review-tasks/{task_id}/downloads/report") as response:
                report_content = response.read().decode("utf-8")
                report_headers = dict(response.headers.items())

            self.assertIn("# 审查报告", report_content)
            self.assertIn("## 报告说明", report_content)
            self.assertIn("attachment;", report_headers["Content-Disposition"])

            with urllib.request.urlopen(
                f"{server.base_url}/api/v1/review-tasks/{task_id}/downloads/conclusion"
            ) as response:
                conclusion_content = response.read().decode("utf-8")

            self.assertIn("# 最终结论", conclusion_content)
            self.assertIn("## 风险统计", conclusion_content)

    def test_result_endpoint_returns_409_when_not_ready(self):
        with TestServerContext() as server:
            boundary = f"boundary-{uuid4().hex}"
            body = build_multipart_body(boundary, "招标文件.pdf", b"fake-pdf-content")
            request = urllib.request.Request(
                f"{server.base_url}/api/v1/review-tasks",
                data=body,
                method="POST",
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
            with urllib.request.urlopen(request) as response:
                payload = json.loads(response.read().decode("utf-8"))

            with self.assertRaises(urllib.error.HTTPError) as context:
                urllib.request.urlopen(f"{server.base_url}/api/v1/review-tasks/{payload['task_id']}/result")

            self.assertEqual(context.exception.code, 409)
            error_payload = json.loads(context.exception.read().decode("utf-8"))
            self.assertEqual(error_payload["error_code"], "RESULT_NOT_READY")

    def test_result_and_download_endpoints_return_409_when_task_failed(self):
        class FailingDocumentRepository(JsonRepository):
            def save_document(self, document):  # type: ignore[override]
                raise OSError("document write failed")

        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = FailingDocumentRepository(Path(runtime_dir))
            service = UploadService(repository)

            with self.assertRaises(UploadProcessingError):
                service.create_review_task(UploadFile(filename="招标文件.pdf", content=b"fake-pdf-content"))

            task_payload = json.loads((Path(runtime_dir) / "metadata" / "review_tasks.json").read_text(encoding="utf-8"))
            task_id = next(iter(task_payload.keys()))

            with self.assertRaises(ResultAccessError) as result_context:
                service.get_review_result(task_id)
            self.assertEqual(result_context.exception.error_code, "RESULT_FAILED")

            with self.assertRaises(ResultAccessError) as download_context:
                service.download_result_file(task_id, "report")
            self.assertEqual(download_context.exception.error_code, "RESULT_FAILED")

    def test_download_endpoint_returns_404_for_invalid_file_type(self):
        with TestServerContext() as server:
            boundary = f"boundary-{uuid4().hex}"
            body = build_multipart_body(
                boundary,
                "招标文件.docx",
                (
                    "第一章 资格要求\n"
                    "1.1 供应商资格\n"
                    "供应商须本地注册并在本地办公。\n"
                    "第二章 评分办法\n"
                    "2.1 评分标准\n"
                    "采用综合评价并可酌情打分。\n"
                ).encode("utf-8"),
            )
            request = urllib.request.Request(
                f"{server.base_url}/api/v1/review-tasks",
                data=body,
                method="POST",
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )
            with urllib.request.urlopen(request) as response:
                payload = json.loads(response.read().decode("utf-8"))

            task_id = payload["task_id"]
            WorkerRunner(JsonRepository(server.runtime_dir), Path(__file__).resolve().parent.parent).run_until_idle()

            with self.assertRaises(urllib.error.HTTPError) as context:
                urllib.request.urlopen(f"{server.base_url}/api/v1/review-tasks/{task_id}/downloads/unknown")

            self.assertEqual(context.exception.code, 404)
            error_payload = json.loads(context.exception.read().decode("utf-8"))
            self.assertEqual(error_payload["error_code"], "DOWNLOAD_NOT_FOUND")

    def test_result_page_renders_failed_task_feedback(self):
        class FailingDocumentRepository(JsonRepository):
            def save_document(self, document):  # type: ignore[override]
                raise OSError("document write failed")

        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = FailingDocumentRepository(Path(runtime_dir))
            service = UploadService(repository)

            with self.assertRaises(UploadProcessingError):
                service.create_review_task(UploadFile(filename="招标文件.pdf", content=b"fake-pdf-content"))

            task_payload = json.loads((Path(runtime_dir) / "metadata" / "review_tasks.json").read_text(encoding="utf-8"))
            task_id = next(iter(task_payload.keys()))

            server = ReviewHTTPServer(("127.0.0.1", 0), service)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                host, port = server.server_address
                with urllib.request.urlopen(f"http://{host}:{port}/review-tasks/{task_id}/page") as response:
                    html = response.read().decode("utf-8")
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=2)

            self.assertIn("任务失败", html)
            self.assertIn("错误码", html)
            self.assertIn("重新查看当前页面", html)
            self.assertIn("重新提交文件", html)

    def test_create_review_task_and_query_status(self):
        with TestServerContext() as server:
            boundary = f"boundary-{uuid4().hex}"
            body = build_multipart_body(boundary, "招标文件.pdf", b"fake-pdf-content")
            request = urllib.request.Request(
                f"{server.base_url}/api/v1/review-tasks",
                data=body,
                method="POST",
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )

            with urllib.request.urlopen(request) as response:
                payload = json.loads(response.read().decode("utf-8"))

            self.assertEqual(payload["status"], "uploaded")
            self.assertEqual(payload["file_type"], "PDF")
            task_id = payload["task_id"]

            with urllib.request.urlopen(f"{server.base_url}/api/v1/review-tasks/{task_id}") as response:
                status_payload = json.loads(response.read().decode("utf-8"))

            self.assertEqual(status_payload["task_id"], task_id)
            self.assertEqual(status_payload["status"], "uploaded")
            queue_file = server.runtime_dir / "queues" / "parse" / f"{task_id}.json"
            self.assertTrue(queue_file.exists())
            tasks_path = server.runtime_dir / "metadata" / "review_tasks.json"
            task_payload = json.loads(tasks_path.read_text(encoding="utf-8"))
            self.assertEqual(task_payload[task_id]["internal_status"], "upload_validated")

    def test_reject_unsupported_file_type(self):
        with TestServerContext() as server:
            boundary = f"boundary-{uuid4().hex}"
            body = build_multipart_body(boundary, "招标文件.txt", b"plain-text")
            request = urllib.request.Request(
                f"{server.base_url}/api/v1/review-tasks",
                data=body,
                method="POST",
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            )

            with self.assertRaises(urllib.error.HTTPError) as context:
                urllib.request.urlopen(request)

            self.assertEqual(context.exception.code, 415)
            payload = json.loads(context.exception.read().decode("utf-8"))
            self.assertEqual(payload["error_code"], "UNSUPPORTED_FILE_TYPE")

    def test_repository_write_is_safe_under_concurrent_uploads(self):
        with TestServerContext() as server:
            service = create_service()
            errors: list[Exception] = []
            task_ids: list[str] = []

            def worker(index: int) -> None:
                try:
                    payload = service.create_review_task(
                        UploadFile(filename=f"招标文件-{index}.pdf", content=f"file-{index}".encode("utf-8"))
                    )
                    task_ids.append(payload["task_id"])
                except Exception as exc:  # pragma: no cover - for failure capture only
                    errors.append(exc)

            threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()

            self.assertFalse(errors)
            self.assertEqual(len(task_ids), 8)
            tasks_path = server.runtime_dir / "metadata" / "review_tasks.json"
            task_payload = json.loads(tasks_path.read_text(encoding="utf-8"))
            self.assertEqual(len(task_payload), 8)

    def test_mark_task_failed_when_document_persist_fails(self):
        class FailingDocumentRepository(JsonRepository):
            def save_document(self, document):  # type: ignore[override]
                raise OSError("document write failed")

        with tempfile.TemporaryDirectory() as runtime_dir:
            repository = FailingDocumentRepository(Path(runtime_dir))
            service = UploadService(repository)

            with self.assertRaises(UploadProcessingError) as context:
                service.create_review_task(UploadFile(filename="招标文件.pdf", content=b"fake-pdf-content"))

            self.assertEqual(context.exception.error_code, "UPLOAD_PERSIST_FAILED")
            tasks_path = Path(runtime_dir) / "metadata" / "review_tasks.json"
            task_payload = json.loads(tasks_path.read_text(encoding="utf-8"))
            self.assertEqual(len(task_payload), 1)
            saved_task = next(iter(task_payload.values()))
            self.assertEqual(saved_task["internal_status"], "failed")
            self.assertEqual(saved_task["status"], "failed")
            self.assertEqual(saved_task["error_code"], "UPLOAD_PERSIST_FAILED")
