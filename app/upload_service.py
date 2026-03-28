from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from app.models import build_document_record, build_review_task
from app.repository import JsonRepository


SUPPORTED_TYPES = {
    ".pdf": "PDF",
    ".doc": "Word",
    ".docx": "Word",
}


class UploadValidationError(Exception):
    def __init__(self, status_code: int, error_code: str, error_message: str):
        super().__init__(error_message)
        self.status_code = status_code
        self.error_code = error_code
        self.error_message = error_message

    def to_response(self) -> tuple[int, dict[str, str]]:
        return self.status_code, {
            "error_code": self.error_code,
            "error_message": self.error_message,
        }


@dataclass
class UploadFile:
    filename: str
    content: bytes


class UploadService:
    def __init__(self, repository: JsonRepository):
        self.repository = repository

    def create_review_task(self, upload_file: UploadFile) -> dict[str, str]:
        file_type = self._validate_upload(upload_file)
        task_id = f"task_{uuid4().hex[:12]}"
        project_id = f"project_{uuid4().hex[:12]}"
        document_id = f"document_{uuid4().hex[:12]}"

        stored_path = self.repository.save_upload(task_id, upload_file.filename, upload_file.content)
        document = build_document_record(
            document_id=document_id,
            project_id=project_id,
            file_name=upload_file.filename,
            file_type=file_type,
            source_uri=str(stored_path),
        )
        task = build_review_task(
            task_id=task_id,
            project_id=project_id,
            document_id=document_id,
            file_name=upload_file.filename,
            file_type=file_type,
        )
        self.repository.save_document(document)
        self.repository.save_task(task)
        self.repository.enqueue_parse_job(task)
        return task.to_upload_response()

    def get_review_task_status(self, task_id: str) -> dict[str, str | None] | None:
        task = self.repository.get_task(task_id)
        if task is None:
            return None
        return task.to_status_response()

    @staticmethod
    def _validate_upload(upload_file: UploadFile) -> str:
        if not upload_file.filename:
            raise UploadValidationError(400, "MISSING_FILE_NAME", "缺少文件名。")
        if not upload_file.content:
            raise UploadValidationError(400, "EMPTY_FILE", "上传文件不能为空。")
        extension = Path(upload_file.filename).suffix.lower()
        file_type = SUPPORTED_TYPES.get(extension)
        if file_type is None:
            raise UploadValidationError(415, "UNSUPPORTED_FILE_TYPE", "仅支持 PDF 或 Word 文件。")
        return file_type
