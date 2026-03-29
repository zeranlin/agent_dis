from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.models import build_review_result_record
from app.result_presenter import count_risk_groups, group_risks
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
            risk_groups = group_risks(risks=risks, repository=self.repository)
            risk_counts = count_risk_groups(risk_groups)
            risk_count_high = risk_counts["high"]
            risk_count_medium = risk_counts["medium"]
            risk_count_low = risk_counts["low"]

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
                risk_groups=risk_groups,
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
        return f"本文件归并后存在 {risk_count_high} 组高风险问题和 {risk_count_medium} 组中风险问题，建议优先复核品牌指向、合同责任失衡和资格门槛偏严条款。"
    if risk_count_medium > 0:
        return f"本文件未发现高风险问题，但归并后存在 {risk_count_medium} 组中风险问题，建议优先复核资格门槛、评分条款和商务要求。"
    if risk_count_low > 0:
        return f"本文件未发现高风险或中风险问题，当前归并后仅识别到 {risk_count_low} 组低风险提示。"
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
        "## 文件概览\n\n"
        f"- 文件名称：{file_name}\n"
        "\n## 结论摘要\n\n"
        f"- 总体结论：{overall_conclusion}\n"
        "\n## 风险统计\n\n"
        "- 以下数量为按同条款同规则归并后的风险组数量。\n"
        f"- 高风险组数量：{risk_count_high}\n"
        f"- 中风险组数量：{risk_count_medium}\n"
        f"- 低风险组数量：{risk_count_low}\n"
        "\n## 处理建议\n\n"
        "- 建议审核人员优先复核高风险与中风险风险组，再结合原文证据完成人工判断。\n"
    )


def build_report_markdown(
    *,
    file_name: str,
    overall_conclusion: str,
    risk_groups: list[dict[str, object]],
) -> str:
    focus_summary = "、".join(
        title
        for title in []
    )
    if risk_groups:
        focus_titles: list[str] = []
        for risk_group in risk_groups:
            title = str(risk_group["risk_title"])
            if title and title not in focus_titles:
                focus_titles.append(title)
            if len(focus_titles) >= 3:
                break
        focus_summary = "、".join(focus_titles)

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
        "## 报告说明",
        "",
        "- 本报告基于当前 V1 最小规则包和解析结果自动生成。",
        "- 风险结论仅用于辅助审核，不直接替代人工定性。",
        "- 当前风险明细按同条款同规则做轻量归并后展示，更接近人工复核视角。",
        f"- 当前优先关注：{focus_summary or '无'}。",
        "",
        "## 风险组明细",
        "",
    ]
    if not risk_groups:
        lines.extend(
            [
                "当前未识别到明显风险。",
                "",
            ]
        )
        return "\n".join(lines)

    for index, risk_group in enumerate(risk_groups, start=1):
        lines.extend(
            [
                f"### 风险组 {index}",
                "",
                f"- 风险标题：{risk_group['risk_title']}",
                f"- 风险级别：{risk_group['risk_level']}",
                f"- 规则编号：{risk_group['rule_code']}",
                f"- 规则域：{risk_group['rule_domain']}",
                f"- 章节上下文：{risk_group['chapter_title'] or '无'}",
                f"- 业务单元：{risk_group['unit_label'] or '未标注'}",
                f"- 片段类型：{risk_group['clause_type'] or '未标注'}",
                f"- 命中位置：{risk_group['location_label']}",
                f"- 归并命中数：{risk_group['merged_hit_count']}",
                f"- 风险说明：{risk_group['risk_description']}",
                f"- 审查说明：{risk_group['review_reasoning']}",
                f"- 证据片段：{risk_group['evidence_text']}",
                f"- 证据说明：{risk_group['evidence_note']}",
                "",
            ]
        )
    return "\n".join(lines)
