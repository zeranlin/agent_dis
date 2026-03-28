from __future__ import annotations


SEVERITY_ORDER = {"高": 0, "中": 1, "低": 2}


def extract_chapter_title(location_label: str, *, default: str = "") -> str:
    if " / " not in location_label:
        return default
    return location_label.split(" / ", 1)[0]


def extract_clause_type(review_reasoning: str, *, default: str = "") -> str:
    if "条款片段" in review_reasoning:
        return "条款片段"
    if "段落片段" in review_reasoning:
        return "段落片段"
    return default


def sort_risks_for_display(risks: list[object]) -> list[object]:
    return sorted(
        risks,
        key=lambda item: (SEVERITY_ORDER.get(item.risk_level, 9), item.created_at),
    )


def build_top_risk_payload(risk: object) -> dict[str, object]:
    return {
        "risk_id": risk.risk_id,
        "risk_title": risk.risk_title,
        "risk_level": risk.risk_level,
        "location_label": risk.location_label,
        "chapter_title": extract_chapter_title(risk.location_label),
        "clause_type": extract_clause_type(risk.review_reasoning),
        "risk_description": risk.risk_description,
        "review_reasoning": risk.review_reasoning,
    }


def build_downloadable_file_payloads(task_id: str) -> list[dict[str, str]]:
    return [
        {
            "name": "最终结论.md",
            "type": "markdown",
            "file_key": "conclusion",
            "label": "下载最终结论",
            "description": "适合先快速查看整体结论和风险统计。",
            "url": f"/api/v1/review-tasks/{task_id}/downloads/conclusion",
        },
        {
            "name": "审查报告.md",
            "type": "markdown",
            "file_key": "report",
            "label": "下载审查报告",
            "description": "适合继续核对风险明细、证据片段和审查说明。",
            "url": f"/api/v1/review-tasks/{task_id}/downloads/report",
        },
    ]


def build_completed_page_payload(
    *,
    result_payload: dict[str, object],
    file_name: str,
) -> dict[str, object]:
    summary_title = str(result_payload["summary_title"])
    overall_conclusion = str(result_payload["overall_conclusion"])
    return {
        "page_state": "completed",
        "status_label": "结果已生成",
        "summary_title": summary_title,
        "overall_conclusion": overall_conclusion,
        "title": summary_title,
        "file_name": file_name,
        "message": overall_conclusion,
        "conclusion_markdown": result_payload["conclusion_markdown"],
        "report_markdown": result_payload["report_markdown"],
        "risk_count_summary": result_payload["risk_count_summary"],
        "top_risks": result_payload["top_risks"],
        "downloadable_files": result_payload["downloadable_files"],
        "status_api_url": result_payload["status_api_url"],
        "result_api_url": result_payload["result_api_url"],
        "page_url": result_payload["page_url"],
        "generated_at": result_payload["generated_at"],
    }


def build_failed_page_payload(
    *,
    task_id: str,
    file_name: str,
    status_message: str,
    error_code: str | None,
) -> dict[str, object]:
    return {
        "page_state": "failed",
        "status_label": "任务失败",
        "summary_title": "审查未完成",
        "overall_conclusion": status_message,
        "title": "审查未完成",
        "file_name": file_name,
        "message": status_message,
        "error_code": error_code,
        "status_api_url": f"/api/v1/review-tasks/{task_id}",
        "page_url": f"/review-tasks/{task_id}/page",
    }


def build_reviewing_page_payload(
    *,
    task_id: str,
    file_name: str,
    status_message: str,
) -> dict[str, object]:
    return {
        "page_state": "reviewing",
        "status_label": "审核中",
        "summary_title": "审查进行中",
        "overall_conclusion": status_message,
        "title": "审查进行中",
        "file_name": file_name,
        "message": status_message,
        "status_api_url": f"/api/v1/review-tasks/{task_id}",
        "result_api_url": f"/api/v1/review-tasks/{task_id}/result",
        "page_url": f"/review-tasks/{task_id}/page",
    }
