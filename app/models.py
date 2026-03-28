from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import UTC, datetime


OUTWARD_STATUS_BY_INTERNAL = {
    "created": "uploaded",
    "upload_validated": "uploaded",
    "parsing": "reviewing",
    "parsed": "reviewing",
    "review_queued": "reviewing",
    "reviewing_chapters": "reviewing",
    "reviewing_clauses": "reviewing",
    "aggregating": "reviewing",
    "completed": "completed",
    "failed": "failed",
}


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


@dataclass
class ReviewTask:
    task_id: str
    project_id: str
    document_id: str
    file_name: str
    file_type: str
    status: str
    internal_status: str
    status_message: str
    error_code: str | None
    error_message: str | None
    retry_count: int
    created_at: str
    started_at: str | None
    completed_at: str | None
    updated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_upload_response(self) -> dict[str, str]:
        return {
            "task_id": self.task_id,
            "file_name": self.file_name,
            "file_type": self.file_type,
            "status": self.status,
            "message": self.status_message,
        }

    def to_status_response(self) -> dict[str, str | None]:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "file_name": self.file_name,
            "started_at": self.started_at,
            "message": self.status_message,
        }

    def transition_to(self, internal_status: str, status_message: str) -> None:
        self.internal_status = internal_status
        self.status = OUTWARD_STATUS_BY_INTERNAL[internal_status]
        self.status_message = status_message
        self.updated_at = now_iso()


@dataclass
class DocumentRecord:
    document_id: str
    project_id: str
    document_name: str
    document_type: str
    document_format: str
    source_uri: str
    storage_bucket: str
    raw_text: str
    parsed_status: str
    page_count: int
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def build_review_task(
    *,
    task_id: str,
    project_id: str,
    document_id: str,
    file_name: str,
    file_type: str,
) -> ReviewTask:
    timestamp = now_iso()
    internal_status = "created"
    return ReviewTask(
        task_id=task_id,
        project_id=project_id,
        document_id=document_id,
        file_name=file_name,
        file_type=file_type,
        status=OUTWARD_STATUS_BY_INTERNAL[internal_status],
        internal_status=internal_status,
        status_message="任务已创建，正在校验上传文件。",
        error_code=None,
        error_message=None,
        retry_count=0,
        created_at=timestamp,
        started_at=None,
        completed_at=None,
        updated_at=timestamp,
    )


def build_document_record(
    *,
    document_id: str,
    project_id: str,
    file_name: str,
    file_type: str,
    source_uri: str,
) -> DocumentRecord:
    return DocumentRecord(
        document_id=document_id,
        project_id=project_id,
        document_name=file_name,
        document_type="招标文件正文",
        document_format=file_type,
        source_uri=source_uri,
        storage_bucket="local",
        raw_text="",
        parsed_status="pending",
        page_count=0,
        created_at=now_iso(),
    )
