from __future__ import annotations

from pathlib import Path

from app.asset_loader import ReviewAssetLoader
from app.models import ReviewRuntimeInput
from app.repository import JsonRepository


DEFAULT_OUTPUT_SCHEMA = {
    "risk_item_fields": [
        "risk_id",
        "rule_code",
        "rule_name",
        "risk_level",
        "execution_level",
        "module_type",
        "unit_type",
        "unit_label",
        "unit_name",
        "review_unit_id",
        "chapter_title",
        "clause_type",
        "location_label",
        "risk_description",
        "review_reasoning",
    ],
    "evidence_item_fields": [
        "evidence_id",
        "module_type",
        "unit_type",
        "unit_label",
        "unit_name",
        "review_unit_id",
        "chapter_title",
        "clause_type",
        "quoted_text",
        "location_label",
        "evidence_note",
    ],
}


class ReviewInputAssembler:
    def __init__(self, repository: JsonRepository, asset_loader: ReviewAssetLoader):
        self.repository = repository
        self.asset_loader = asset_loader

    def assemble(self, task_id: str) -> ReviewRuntimeInput:
        task = self.repository.get_task(task_id)
        if task is None:
            raise ValueError(f"任务不存在: {task_id}")
        document = self.repository.get_document(task.document_id)
        if document is None:
            raise ValueError(f"文件不存在: {task.document_id}")
        clauses = self.repository.list_clauses_by_document(task.document_id)
        if not clauses:
            raise ValueError(f"条款不存在: {task.document_id}")

        return ReviewRuntimeInput(
            task_id=task.task_id,
            document_id=document.document_id,
            file_name=document.document_name,
            prompt_text=self.asset_loader.load_prompt_asset().content_text,
            rules=self.asset_loader.load_rule_pack(),
            clauses=clauses,
            output_schema=DEFAULT_OUTPUT_SCHEMA,
        )


def create_review_assembler(repository: JsonRepository, root_dir: Path) -> ReviewInputAssembler:
    return ReviewInputAssembler(repository, ReviewAssetLoader(root_dir))
