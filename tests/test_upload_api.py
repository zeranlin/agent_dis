from __future__ import annotations

import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from uuid import uuid4

from app.server import ReviewHTTPServer, create_service


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
