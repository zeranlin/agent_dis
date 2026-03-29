from __future__ import annotations

import contextlib
import fcntl
import json
import os
import threading
from pathlib import Path

from app.models import (
    BlockRecord,
    ChapterRecord,
    ClauseRecord,
    DocumentRecord,
    EvidenceItemRecord,
    ReviewResultRecord,
    ReviewTask,
    RiskItemRecord,
)


class JsonRepository:
    _locks: dict[Path, threading.Lock] = {}
    _locks_guard = threading.Lock()

    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.metadata_dir = self.root_dir / "metadata"
        self.upload_dir = self.root_dir / "uploads"
        self.queue_dir = self.root_dir / "queues" / "parse"
        self.review_queue_dir = self.root_dir / "queues" / "review"
        self.result_queue_dir = self.root_dir / "queues" / "result"
        self.output_dir = self.root_dir / "outputs"
        self.report_dir = self.output_dir / "reports"
        self.conclusion_dir = self.output_dir / "conclusions"
        self.metadata_dir.mkdir(parents=True, exist_ok=True)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.queue_dir.mkdir(parents=True, exist_ok=True)
        self.review_queue_dir.mkdir(parents=True, exist_ok=True)
        self.result_queue_dir.mkdir(parents=True, exist_ok=True)
        self.report_dir.mkdir(parents=True, exist_ok=True)
        self.conclusion_dir.mkdir(parents=True, exist_ok=True)
        self.tasks_path = self.metadata_dir / "review_tasks.json"
        self.documents_path = self.metadata_dir / "documents.json"
        self.chapters_path = self.metadata_dir / "chapters.json"
        self.clauses_path = self.metadata_dir / "clauses.json"
        self.blocks_path = self.metadata_dir / "blocks.json"
        self.risks_path = self.metadata_dir / "risks.json"
        self.evidences_path = self.metadata_dir / "evidences.json"
        self.results_path = self.metadata_dir / "results.json"

    def save_task(self, task: ReviewTask) -> None:
        self._update_json_mapping(self.tasks_path, task.task_id, task.to_dict())

    def get_task(self, task_id: str) -> ReviewTask | None:
        tasks = self._read_json(self.tasks_path)
        data = tasks.get(task_id)
        if data is None:
            return None
        return ReviewTask(**data)

    def save_document(self, document: DocumentRecord) -> None:
        self._update_json_mapping(self.documents_path, document.document_id, document.to_dict())

    def get_document(self, document_id: str) -> DocumentRecord | None:
        documents = self._read_json(self.documents_path)
        data = documents.get(document_id)
        if data is None:
            return None
        return DocumentRecord(**data)

    def save_chapter(self, chapter: ChapterRecord) -> None:
        self._update_json_mapping(self.chapters_path, chapter.chapter_id, chapter.to_dict())

    def save_clause(self, clause: ClauseRecord) -> None:
        self._update_json_mapping(self.clauses_path, clause.clause_id, clause.to_dict())

    def save_block(self, block: BlockRecord) -> None:
        self._update_json_mapping(self.blocks_path, block.block_id, block.to_dict())

    def list_blocks_by_document(self, document_id: str) -> list[BlockRecord]:
        blocks = self._read_json(self.blocks_path)
        block_records = [
            BlockRecord(**payload)
            for payload in blocks.values()
            if payload["document_id"] == document_id
        ]
        return sorted(block_records, key=lambda item: item.order_index)

    def list_clauses_by_document(self, document_id: str) -> list[ClauseRecord]:
        clauses = self._read_json(self.clauses_path)
        clause_records = [
            ClauseRecord(**payload)
            for payload in clauses.values()
            if payload["document_id"] == document_id
        ]
        return sorted(clause_records, key=lambda item: item.clause_order)

    def get_clause(self, clause_id: str) -> ClauseRecord | None:
        clauses = self._read_json(self.clauses_path)
        payload = clauses.get(clause_id)
        if payload is None:
            return None
        return ClauseRecord(**payload)

    def save_risk(self, risk: RiskItemRecord) -> None:
        self._update_json_mapping(self.risks_path, risk.risk_id, risk.to_dict())

    def save_evidence(self, evidence: EvidenceItemRecord) -> None:
        self._update_json_mapping(self.evidences_path, evidence.evidence_id, evidence.to_dict())

    def list_risks_by_task(self, task_id: str) -> list[RiskItemRecord]:
        risks = self._read_json(self.risks_path)
        risk_records = [
            RiskItemRecord(**payload)
            for payload in risks.values()
            if payload["task_id"] == task_id
        ]
        return sorted(risk_records, key=lambda item: item.created_at)

    def list_evidences_by_risk(self, risk_id: str) -> list[EvidenceItemRecord]:
        evidences = self._read_json(self.evidences_path)
        evidence_records = [
            EvidenceItemRecord(**payload)
            for payload in evidences.values()
            if payload["risk_id"] == risk_id
        ]
        return sorted(evidence_records, key=lambda item: item.evidence_id)

    def save_result(self, result: ReviewResultRecord) -> None:
        lock = self._lock_for(self.results_path)
        with lock:
            with self._process_lock(self.results_path):
                current_payload = self._read_json(self.results_path)
                filtered_payload = {
                    key: value
                    for key, value in current_payload.items()
                    if value.get("task_id") != result.task_id
                }
                filtered_payload[result.result_id] = result.to_dict()
                self._write_json(self.results_path, filtered_payload)

    def get_result_by_task(self, task_id: str) -> ReviewResultRecord | None:
        results = self._read_json(self.results_path)
        matched_results = [
            ReviewResultRecord(**payload)
            for payload in results.values()
            if payload["task_id"] == task_id
        ]
        if not matched_results:
            return None
        matched_results.sort(key=lambda item: item.generated_at, reverse=True)
        return matched_results[0]

    def read_report_markdown(self, task_id: str) -> str | None:
        target_path = self.report_dir / f"{task_id}-审查报告.md"
        if not target_path.exists():
            return None
        return target_path.read_text(encoding="utf-8")

    def read_conclusion_markdown(self, task_id: str) -> str | None:
        target_path = self.conclusion_dir / f"{task_id}-最终结论.md"
        if not target_path.exists():
            return None
        return target_path.read_text(encoding="utf-8")

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

    def enqueue_review_job(self, task: ReviewTask) -> Path:
        queue_path = self.review_queue_dir / f"{task.task_id}.json"
        payload = {
            "task_id": task.task_id,
            "document_id": task.document_id,
            "internal_status": task.internal_status,
        }
        self._write_json(queue_path, payload)
        return queue_path

    def enqueue_result_job(self, task: ReviewTask) -> Path:
        queue_path = self.result_queue_dir / f"{task.task_id}.json"
        payload = {
            "task_id": task.task_id,
            "document_id": task.document_id,
            "internal_status": task.internal_status,
        }
        self._write_json(queue_path, payload)
        return queue_path

    def list_parse_jobs(self) -> list[Path]:
        return sorted(self.queue_dir.glob("*.json"))

    def list_review_jobs(self) -> list[Path]:
        return sorted(self.review_queue_dir.glob("*.json"))

    def list_result_jobs(self) -> list[Path]:
        return sorted(self.result_queue_dir.glob("*.json"))

    def read_parse_job(self, path: Path) -> dict[str, object]:
        return self._read_json(path)

    def delete_parse_job(self, path: Path) -> None:
        if path.exists():
            path.unlink()

    def read_review_job(self, path: Path) -> dict[str, object]:
        return self._read_json(path)

    def delete_review_job(self, path: Path) -> None:
        if path.exists():
            path.unlink()

    def read_result_job(self, path: Path) -> dict[str, object]:
        return self._read_json(path)

    def delete_result_job(self, path: Path) -> None:
        if path.exists():
            path.unlink()

    def save_report_markdown(self, task_id: str, content: str) -> Path:
        target_path = self.report_dir / f"{task_id}-审查报告.md"
        target_path.write_text(content, encoding="utf-8")
        return target_path

    def save_conclusion_markdown(self, task_id: str, content: str) -> Path:
        target_path = self.conclusion_dir / f"{task_id}-最终结论.md"
        target_path.write_text(content, encoding="utf-8")
        return target_path

    def _update_json_mapping(self, path: Path, record_id: str, payload: dict[str, object]) -> None:
        lock = self._lock_for(path)
        with lock:
            with self._process_lock(path):
                current_payload = self._read_json(path)
                current_payload[record_id] = payload
                self._write_json(path, current_payload)

    @classmethod
    def _lock_for(cls, path: Path) -> threading.Lock:
        with cls._locks_guard:
            if path not in cls._locks:
                cls._locks[path] = threading.Lock()
            return cls._locks[path]

    @staticmethod
    def _read_json(path: Path) -> dict[str, object]:
        if not path.exists():
            return {}
        return json.loads(path.read_text(encoding="utf-8"))

    @staticmethod
    def _write_json(path: Path, payload: dict[str, object]) -> None:
        temp_path = path.with_suffix(
            f"{path.suffix}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        temp_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        temp_path.replace(path)

    @staticmethod
    @contextlib.contextmanager
    def _process_lock(path: Path):
        lock_path = path.with_suffix(f"{path.suffix}.lock")
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        with lock_path.open("w", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
