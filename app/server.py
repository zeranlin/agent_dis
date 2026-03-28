from __future__ import annotations

import json
import os
from email.parser import BytesParser
from email.policy import default
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from urllib.parse import quote

from app.result_page import render_missing_page, render_result_page
from app.repository import JsonRepository
from app.upload_service import ResultAccessError, UploadFile, UploadProcessingError, UploadService, UploadValidationError


def build_runtime_root() -> Path:
    env_root = os.environ.get("AGENT_DIS_RUNTIME_DIR")
    if env_root:
        return Path(env_root)
    return Path("/tmp/agent_dis_runtime")


def create_service() -> UploadService:
    return UploadService(JsonRepository(build_runtime_root()))


def parse_multipart_file(content_type: str, body: bytes) -> UploadFile:
    message = BytesParser(policy=default).parsebytes(
        f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n".encode("utf-8") + body
    )
    if not message.is_multipart():
        raise UploadValidationError(400, "INVALID_MULTIPART", "请求必须使用 multipart/form-data。")

    for part in message.iter_parts():
        name = part.get_param("name", header="content-disposition")
        if name != "file":
            continue
        filename = part.get_filename() or ""
        content = part.get_payload(decode=True) or b""
        return UploadFile(filename=filename, content=content)

    raise UploadValidationError(400, "MISSING_FILE_FIELD", "缺少 file 上传字段。")


class ReviewRequestHandler(BaseHTTPRequestHandler):
    server_version = "agent_dis/0.1"

    def do_POST(self) -> None:
        if self.path != "/api/v1/review-tasks":
            self._write_json(HTTPStatus.NOT_FOUND, {"error_code": "NOT_FOUND", "error_message": "接口不存在。"})
            return

        try:
            upload_file = self._read_upload_file()
            response = self.server.upload_service.create_review_task(upload_file)
            self._write_json(HTTPStatus.CREATED, response)
        except UploadValidationError as exc:
            status_code, payload = exc.to_response()
            self._write_json(status_code, payload)
        except UploadProcessingError as exc:
            status_code, payload = exc.to_response()
            self._write_json(status_code, payload)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path.startswith("/review-tasks/") and path.endswith("/page"):
            task_id = path.removeprefix("/review-tasks/").removesuffix("/page")
            if not task_id or "/" in task_id:
                self._write_html(HTTPStatus.NOT_FOUND, render_missing_page())
                return
            try:
                payload = self.server.upload_service.get_result_page_payload(task_id)
                self._write_html(HTTPStatus.OK, render_result_page(payload))
            except ResultAccessError as exc:
                if exc.error_code == "TASK_NOT_FOUND":
                    self._write_html(HTTPStatus.NOT_FOUND, render_missing_page())
                else:
                    status_code, payload = exc.to_response()
                    self._write_json(status_code, payload)
            return

        task_prefix = "/api/v1/review-tasks/"
        if not path.startswith(task_prefix):
            self._write_json(HTTPStatus.NOT_FOUND, {"error_code": "NOT_FOUND", "error_message": "接口不存在。"})
            return

        if path.endswith("/result"):
            task_id = path.removeprefix(task_prefix).removesuffix("/result")
            if not task_id or "/" in task_id:
                self._write_json(HTTPStatus.NOT_FOUND, {"error_code": "NOT_FOUND", "error_message": "接口不存在。"})
                return
            try:
                payload = self.server.upload_service.get_review_result(task_id)
                self._write_json(HTTPStatus.OK, payload)
            except ResultAccessError as exc:
                status_code, payload = exc.to_response()
                self._write_json(status_code, payload)
            return

        download_marker = "/downloads/"
        if download_marker in path:
            task_and_suffix = path.removeprefix(task_prefix)
            task_id, _, file_type = task_and_suffix.partition(download_marker)
            if not task_id or not file_type or "/" in task_id or "/" in file_type:
                self._write_json(HTTPStatus.NOT_FOUND, {"error_code": "NOT_FOUND", "error_message": "接口不存在。"})
                return
            try:
                file_name, content_type, content = self.server.upload_service.download_result_file(task_id, file_type)
                self._write_text(HTTPStatus.OK, content_type, content, download_name=file_name)
            except ResultAccessError as exc:
                status_code, payload = exc.to_response()
                self._write_json(status_code, payload)
            return

        task_id = path.removeprefix(task_prefix)
        if not task_id or "/" in task_id:
            self._write_json(HTTPStatus.NOT_FOUND, {"error_code": "NOT_FOUND", "error_message": "接口不存在。"})
            return

        payload = self.server.upload_service.get_review_task_status(task_id)
        if payload is None:
            self._write_json(HTTPStatus.NOT_FOUND, {"error_code": "TASK_NOT_FOUND", "error_message": "任务不存在。"})
            return
        self._write_json(HTTPStatus.OK, payload)

    def log_message(self, format: str, *args: object) -> None:
        return

    def _read_upload_file(self) -> UploadFile:
        content_type = self.headers.get("Content-Type", "")
        if "multipart/form-data" not in content_type:
            raise UploadValidationError(400, "INVALID_CONTENT_TYPE", "请求必须使用 multipart/form-data。")

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        return parse_multipart_file(content_type, body)

    def _write_json(self, status_code: int, payload: dict[str, object]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _write_text(self, status_code: int, content_type: str, content: str, *, download_name: str | None = None) -> None:
        body = content.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        if download_name is not None:
            ascii_name = "download.md"
            if download_name.endswith(".md"):
                ascii_name = "result.md"
            encoded_name = quote(download_name)
            disposition = f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{encoded_name}"
            self.send_header("Content-Disposition", disposition)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _write_html(self, status_code: int, content: str) -> None:
        body = content.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class ReviewHTTPServer(ThreadingHTTPServer):
    def __init__(self, server_address: tuple[str, int], upload_service: UploadService):
        super().__init__(server_address, ReviewRequestHandler)
        self.upload_service = upload_service


def run_server(host: str = "127.0.0.1", port: int = 8000) -> None:
    upload_service = create_service()
    with ReviewHTTPServer((host, port), upload_service) as server:
        server.serve_forever()


if __name__ == "__main__":
    run_server()
