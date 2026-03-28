from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.asset_loader import ReviewAssetLoader
from app.models import build_evidence_item_record, build_risk_item_record
from app.repository import JsonRepository
from app.review_assembler import ReviewInputAssembler


KEYWORD_MAP = {
    "R1": ["本地注册", "本地办公", "常驻本地"],
    "R5": ["品牌", "型号", "专利"],
    "R9": ["综合评价", "优良中差", "酌情打分"],
}


class ReviewExecutor:
    def __init__(self, repository: JsonRepository, root_dir: Path):
        self.repository = repository
        self.assembler = ReviewInputAssembler(repository, ReviewAssetLoader(root_dir))

    def run_pending_jobs(self) -> int:
        processed_count = 0
        for job_path in self.repository.list_review_jobs():
            self._process_job(job_path)
            processed_count += 1
        return processed_count

    def _process_job(self, job_path: Path) -> None:
        job = self.repository.read_review_job(job_path)
        task = self.repository.get_task(str(job["task_id"]))
        if task is None:
            self.repository.delete_review_job(job_path)
            return

        try:
            task.transition_to("reviewing_clauses", "系统正在执行规则审查。")
            self.repository.save_task(task)

            runtime_input = self.assembler.assemble(task.task_id)
            total_findings = 0

            for clause in runtime_input.clauses:
                for rule in runtime_input.rules:
                    keywords = KEYWORD_MAP.get(str(rule["rule_code"]), [])
                    matched_keyword = next((keyword for keyword in keywords if keyword in clause.clause_text), None)
                    if matched_keyword is None:
                        continue

                    total_findings += 1
                    risk_id = f"risk_{uuid4().hex[:12]}"
                    evidence_id = f"evidence_{uuid4().hex[:12]}"
                    clause_context = f"{clause.chapter_title}的{clause.clause_type}"
                    risk = build_risk_item_record(
                        risk_id=risk_id,
                        task_id=task.task_id,
                        project_id=task.project_id,
                        document_id=task.document_id,
                        clause_id=clause.clause_id,
                        rule=rule,
                        location_label=clause.location_label,
                        risk_description=f"{clause_context}中出现“{matched_keyword}”，命中规则 {rule['rule_code']}。",
                        review_reasoning=(
                            f"当前最小执行骨架在“{clause.location_label}”识别到关键词“{matched_keyword}”，"
                            f"并将其解释为{clause_context}命中规则。"
                        ),
                    )
                    evidence = build_evidence_item_record(
                        evidence_id=evidence_id,
                        risk_id=risk_id,
                        document_id=task.document_id,
                        clause_id=clause.clause_id,
                        quoted_text=clause.clause_text,
                        location_label=clause.location_label,
                        evidence_note=f"{clause_context}原文包含关键词“{matched_keyword}”。",
                    )
                    self.repository.save_risk(risk)
                    self.repository.save_evidence(evidence)

            task.transition_to("aggregating", f"审查执行完成，已生成 {total_findings} 条中间审查结果，待结果汇总。")
            self.repository.save_task(task)
            self.repository.enqueue_result_job(task)
        except Exception as exc:
            task.mark_failed(
                error_code="REVIEW_EXECUTION_FAILED",
                error_message=str(exc),
                status_message="审查执行失败，请检查输入链路。",
            )
            self.repository.save_task(task)
        finally:
            self.repository.delete_review_job(job_path)
