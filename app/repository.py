from __future__ import annotations

import json
from pathlib import Path

from app.models import DocumentRecord, ReviewTask


class JsonRepository:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.metadata_dir = self.root_dir / "metadata"
        self.upload_dir = self.root_dir / "uploads"
        self.queue_dir = self.root_dir / "queues" / "parse"
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_path = self.metadata_dir / "review_tasks.json"
        self.documents_path = self.metadata_dir / "documents.json"

    def save_task(self, task: ReviewTask) -> None:
        tasks = self._read_json(self.tasks_path)
        tasks[task.task_id] = task.to_dict()
        self._write_json(self.tasks_path, tasks)

    def get_task(self, task_id: str) -> ReviewTask | None:
        tasks = self._read_json(self.tasks_path)
        data = tasks.get(task_id)
        if data is None:
            return None
        return ReviewTask(**data)

    def save_document(self, document: DocumentRecord) -> None:
        documents = self._read_json(self.documents_path)
        documents[document.document_id] = document.to_dict()
        self._write_json(self.documents_path, documents)

    def save_upload(self, task_id: str, file_name: str, content: bytes) -> Path:
        target_path = self.upload_dir / f"{task_id}-{file_name}"
        target_path.write_bytes(content)
        return target_path

    def enqueue_parse_job(self, task: ReviewTask) -> Path:
        queue_path = self.queue_dir / f"{task.task_id}.json"
        payload = {
            "task_id": task.task_id,
            "document_id": task.document_id,
            "internal_status": task.internal_status,
        }
        self._write_json(queue_path, payload)
        return queue_path

    @staticmethod
    def _read_json(path: Path) -> dict[str, object]:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(path: Path, payload: dict[str, object]) -> None:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
