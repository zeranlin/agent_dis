from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.models import build_review_result_record
from app.repository import JsonRepository


class ResultAggregator:
    def __init__(self, repository: JsonRepository, root_dir: Path):
        self.repository = repository
        self.root_dir = root_dir

    def run_pending_jobs(self) -> int:
        processed_count = 0
        for job_path in self.repository.list_result_jobs():
            self._process_job(job_path)
            processed_count += 1
        return processed_count

    def _process_job(self, job_path: Path) -> None:
        job = self.repository.read_result_job(job_path)
        task = self.repository.get_task(str(job["task_id"]))
        if task is None:
            self.repository.delete_result_job(job_path)
            return

        try:
            risks = self.repository.list_risks_by_task(task.task_id)
            risk_count_high = sum(1 for risk in risks if risk.risk_level == "高")
            risk_count_medium = sum(1 for risk in risks if risk.risk_level == "中")
            risk_count_low = sum(1 for risk in risks if risk.risk_level == "低")

            overall_conclusion = build_overall_conclusion(
                risk_count_high=risk_count_high,
                risk_count_medium=risk_count_medium,
                risk_count_low=risk_count_low,
            )
            summary_title = "审查已完成"
            conclusion_markdown = build_conclusion_markdown(
                file_name=task.file_name,
                overall_conclusion=overall_conclusion,
                risk_count_high=risk_count_high,
                risk_count_medium=risk_count_medium,
                risk_count_low=risk_count_low,
            )
            report_markdown = build_report_markdown(
                file_name=task.file_name,
                overall_conclusion=overall_conclusion,
                risks=risks,
                repository=self.repository,
            )
            report_path = self.repository.save_report_markdown(task.task_id, report_markdown)
            conclusion_path = self.repository.save_conclusion_markdown(task.task_id, conclusion_markdown)
            result = build_review_result_record(
                result_id=f"result_{uuid4().hex[:12]}",
                task_id=task.task_id,
                project_id=task.project_id,
                document_id=task.document_id,
                summary_title=summary_title,
                overall_conclusion=overall_conclusion,
                report_markdown=report_markdown,
                conclusion_markdown=conclusion_markdown,
                risk_count_high=risk_count_high,
                risk_count_medium=risk_count_medium,
                risk_count_low=risk_count_low,
                report_file_path=str(report_path),
                conclusion_file_path=str(conclusion_path),
            )
            self.repository.save_result(result)
            task.transition_to("completed", "审查结果已生成，可查看最终结论与审查报告。")
            task.completed_at = result.generated_at
            self.repository.save_task(task)
        except Exception as exc:
            task.mark_failed(
                error_code="RESULT_AGGREGATION_FAILED",
                error_message=str(exc),
                status_message="结果汇总失败，请检查中间结果。",
            )
            self.repository.save_task(task)
        finally:
            self.repository.delete_result_job(job_path)


def build_overall_conclusion(*, risk_count_high: int, risk_count_medium: int, risk_count_low: int) -> str:
    if risk_count_high > 0:
        return f"本文件存在 {risk_count_high} 条高风险问题，建议优先复核资格条件、评分规则或定向限制条款。"
    if risk_count_medium > 0:
        return f"本文件未发现高风险问题，但存在 {risk_count_medium} 条中风险问题，建议进一步人工复核。"
    if risk_count_low > 0:
        return f"本文件未发现高风险或中风险问题，当前仅识别到 {risk_count_low} 条低风险提示。"
    return "当前最小审查链路未识别到明显风险，建议结合人工复核继续确认。"


def build_conclusion_markdown(
    *,
    file_name: str,
    overall_conclusion: str,
    risk_count_high: int,
    risk_count_medium: int,
    risk_count_low: int,
) -> str:
    return (
        "# 最终结论\n\n"
        f"- 文件名称：{file_name}\n"
        f"- 总体结论：{overall_conclusion}\n"
        f"- 高风险数量：{risk_count_high}\n"
        f"- 中风险数量：{risk_count_medium}\n"
        f"- 低风险数量：{risk_count_low}\n"
    )


def build_report_markdown(
    *,
    file_name: str,
    overall_conclusion: str,
    risks: list[object],
    repository: JsonRepository,
) -> str:
    lines = [
        "# 审查报告",
        "",
        "## 文件信息",
        "",
        f"- 文件名称：{file_name}",
        "",
        "## 总体结论",
        "",
        overall_conclusion,
        "",
        "## 风险明细",
        "",
    ]
    if not risks:
        lines.extend(
            [
                "当前未识别到明显风险。",
                "",
            ]
        )
        return "\n".join(lines)

    for index, risk in enumerate(risks, start=1):
        evidences = repository.list_evidences_by_risk(risk.risk_id)
        evidence_text = evidences[0].quoted_text if evidences else "无"
        evidence_note = evidences[0].evidence_note if evidences else "无"
        lines.extend(
            [
                f"### 风险 {index}",
                "",
                f"- 风险标题：{risk.risk_title}",
                f"- 风险级别：{risk.risk_level}",
                f"- 规则域：{risk.rule_domain}",
                f"- 命中位置：{risk.location_label}",
                f"- 风险说明：{risk.risk_description}",
                f"- 审查说明：{risk.review_reasoning}",
                f"- 证据片段：{evidence_text}",
                f"- 证据说明：{evidence_note}",
                "",
            ]
        )
    return "\n".join(lines)
