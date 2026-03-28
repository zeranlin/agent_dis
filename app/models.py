from __future__ import annotations

from dataclasses import asdict, dataclass, replace
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

    def mark_failed(self, error_code: str, error_message: str, status_message: str) -> None:
        self.transition_to("failed", status_message)
        self.error_code = error_code
        self.error_message = error_message


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

    def with_updates(self, **changes: object) -> "DocumentRecord":
        return replace(self, **changes)


@dataclass
class ChapterRecord:
    chapter_id: str
    document_id: str
    parent_chapter_id: str | None
    chapter_title: str
    chapter_order: int
    page_start: int
    page_end: int
    chapter_text: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class ClauseRecord:
    clause_id: str
    document_id: str
    chapter_id: str
    clause_type: str
    clause_order: int
    clause_text: str
    normalized_text: str
    location_label: str
    page_start: int
    page_end: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class RiskItemRecord:
    risk_id: str
    task_id: str
    project_id: str
    document_id: str
    clause_id: str
    rule_id: str
    risk_title: str
    risk_level: str
    execution_level: str
    rule_domain: str
    file_module: str
    location_label: str
    risk_description: str
    review_reasoning: str
    status: str
    created_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class EvidenceItemRecord:
    evidence_id: str
    risk_id: str
    document_id: str
    clause_id: str
    evidence_type: str
    quoted_text: str
    location_label: str
    evidence_note: str
    page_start: int
    page_end: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class ReviewRuntimeInput:
    task_id: str
    document_id: str
    file_name: str
    prompt_text: str
    rules: list[dict[str, object]]
    clauses: list[ClauseRecord]
    output_schema: dict[str, object]


@dataclass
class ReviewResultRecord:
    result_id: str
    task_id: str
    project_id: str
    document_id: str
    status: str
    summary_title: str
    overall_conclusion: str
    report_markdown: str
    conclusion_markdown: str
    risk_count_high: int
    risk_count_medium: int
    risk_count_low: int
    report_file_path: str
    conclusion_file_path: str
    generated_at: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    def to_result_response(
        self,
        *,
        file_name: str,
        top_risks: list[dict[str, object]],
    ) -> dict[str, object]:
        return {
            "task_id": self.task_id,
            "status": self.status,
            "file_name": file_name,
            "summary_title": self.summary_title,
            "overall_conclusion": self.overall_conclusion,
            "conclusion_markdown": self.conclusion_markdown,
            "report_markdown": self.report_markdown,
            "page_url": f"/review-tasks/{self.task_id}/page",
            "status_api_url": f"/api/v1/review-tasks/{self.task_id}",
            "result_api_url": f"/api/v1/review-tasks/{self.task_id}/result",
            "risk_count_summary": {
                "high": self.risk_count_high,
                "medium": self.risk_count_medium,
                "low": self.risk_count_low,
            },
            "top_risks": top_risks,
            "generated_at": self.generated_at,
            "downloadable_files": [
                {
                    "name": "最终结论.md",
                    "type": "conclusion_markdown",
                    "url": f"/api/v1/review-tasks/{self.task_id}/downloads/conclusion",
                },
                {
                    "name": "审查报告.md",
                    "type": "report_markdown",
                    "url": f"/api/v1/review-tasks/{self.task_id}/downloads/report",
                },
            ],
        }


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


def build_chapter_record(
    *,
    chapter_id: str,
    document_id: str,
    chapter_title: str,
    chapter_order: int,
    chapter_text: str,
) -> ChapterRecord:
    return ChapterRecord(
        chapter_id=chapter_id,
        document_id=document_id,
        parent_chapter_id=None,
        chapter_title=chapter_title,
        chapter_order=chapter_order,
        page_start=1,
        page_end=1,
        chapter_text=chapter_text,
    )


def build_clause_record(
    *,
    clause_id: str,
    document_id: str,
    chapter_id: str,
    clause_order: int,
    clause_text: str,
    location_label: str,
) -> ClauseRecord:
    return ClauseRecord(
        clause_id=clause_id,
        document_id=document_id,
        chapter_id=chapter_id,
        clause_type="未分类条款",
        clause_order=clause_order,
        clause_text=clause_text,
        normalized_text=" ".join(clause_text.split()),
        location_label=location_label,
        page_start=1,
        page_end=1,
    )


def build_risk_item_record(
    *,
    risk_id: str,
    task_id: str,
    project_id: str,
    document_id: str,
    clause_id: str,
    rule: dict[str, object],
    location_label: str,
    risk_description: str,
    review_reasoning: str,
) -> RiskItemRecord:
    file_module = rule.get("file_module", "")
    if isinstance(file_module, list):
        file_module = "、".join(str(item) for item in file_module)
    return RiskItemRecord(
        risk_id=risk_id,
        task_id=task_id,
        project_id=project_id,
        document_id=document_id,
        clause_id=clause_id,
        rule_id=str(rule["rule_id"]),
        risk_title=str(rule["rule_name"]),
        risk_level=str(rule["risk_level"]),
        execution_level=str(rule["execution_level"]),
        rule_domain=str(rule["rule_domain"]),
        file_module=str(file_module),
        location_label=location_label,
        risk_description=risk_description,
        review_reasoning=review_reasoning,
        status="identified",
        created_at=now_iso(),
    )


def build_evidence_item_record(
    *,
    evidence_id: str,
    risk_id: str,
    document_id: str,
    clause_id: str,
    quoted_text: str,
    location_label: str,
    evidence_note: str,
) -> EvidenceItemRecord:
    return EvidenceItemRecord(
        evidence_id=evidence_id,
        risk_id=risk_id,
        document_id=document_id,
        clause_id=clause_id,
        evidence_type="原文证据",
        quoted_text=quoted_text,
        location_label=location_label,
        evidence_note=evidence_note,
        page_start=1,
        page_end=1,
    )


def build_review_result_record(
    *,
    result_id: str,
    task_id: str,
    project_id: str,
    document_id: str,
    summary_title: str,
    overall_conclusion: str,
    report_markdown: str,
    conclusion_markdown: str,
    risk_count_high: int,
    risk_count_medium: int,
    risk_count_low: int,
    report_file_path: str,
    conclusion_file_path: str,
) -> ReviewResultRecord:
    return ReviewResultRecord(
        result_id=result_id,
        task_id=task_id,
        project_id=project_id,
        document_id=document_id,
        status="completed",
        summary_title=summary_title,
        overall_conclusion=overall_conclusion,
        report_markdown=report_markdown,
        conclusion_markdown=conclusion_markdown,
        risk_count_high=risk_count_high,
        risk_count_medium=risk_count_medium,
        risk_count_low=risk_count_low,
        report_file_path=report_file_path,
        conclusion_file_path=conclusion_file_path,
        generated_at=now_iso(),
    )
