from __future__ import annotations

from collections import OrderedDict
from difflib import SequenceMatcher
import re

SEVERITY_ORDER = {"高": 0, "中": 1, "低": 2}
GENERIC_UNIT_LABELS = {"普通条款", "普通表格行", "不确定审查对象", "未标注"}
GENERIC_RISK_TITLES = {
    "R9": {"评审可解释性规则", "评分项未量化检查"},
    "R12": {"关键条款缺失/责任失衡检查"},
}


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


def extract_unit_label(review_reasoning: str, *, default: str = "") -> str:
    marker = "业务单元："
    if marker not in review_reasoning:
        return default
    unit_part = review_reasoning.split(marker, 1)[1]
    return unit_part.split("，", 1)[0].strip() or default


def sort_risks_for_display(risks: list[object]) -> list[object]:
    return sorted(
        risks,
        key=lambda item: (SEVERITY_ORDER.get(item.risk_level, 9), item.created_at),
    )


def _normalize_text(text: str) -> str:
    return "".join(char for char in text if char.isalnum())


def _unique_texts(values: list[str], *, limit: int | None = None) -> list[str]:
    seen: OrderedDict[str, str] = OrderedDict()
    for value in values:
        cleaned = value.strip()
        if not cleaned:
            continue
        normalized = _normalize_text(cleaned)
        if not normalized or normalized in seen:
            continue
        seen[normalized] = cleaned
        if limit is not None and len(seen) >= limit:
            break
    return list(seen.values())


def merge_texts(values: list[str], *, fallback: str = "无", limit: int | None = 2) -> str:
    unique_values = _unique_texts(values, limit=limit)
    if not unique_values:
        return fallback
    return "；".join(unique_values)


def _trim_display_text(text: str, *, limit: int) -> str:
    cleaned = str(text).strip()
    if len(cleaned) <= limit:
        return cleaned
    return f"{cleaned[: limit - 3].rstrip()}..."


def _normalize_location_label(location_label: str) -> str:
    parts = [part.strip() for part in str(location_label).split(" / ") if part.strip()]
    if not parts:
        return "无"
    normalized_parts = [_trim_display_text(part, limit=42) for part in parts]
    if len(normalized_parts) <= 3:
        return " / ".join(normalized_parts)
    return " / ".join(normalized_parts[:3])


def _normalize_chapter_title(chapter_title: str) -> str:
    title = str(chapter_title).strip()
    if not title:
        return ""
    return _trim_display_text(title, limit=42)


def _format_unit_display(*, unit_label: str, unit_name: str) -> str:
    label = str(unit_label).strip() or "未标注"
    name = str(unit_name).strip()
    if len(name) > 48:
        name = f"{name[:45].rstrip()}..."
    if not name or name in label or label in GENERIC_UNIT_LABELS:
        return label
    return f"{label}（{name}）"


def _normalize_rule_code(rule_id: str) -> str:
    text = str(rule_id).strip()
    matched = re.search(r"R\d+", text, re.IGNORECASE)
    if matched:
        return matched.group(0).upper()
    return text


def _extract_focus_summary(risk_groups: list[dict[str, object]]) -> str:
    focus_titles = _unique_texts([str(group.get("risk_title") or "") for group in risk_groups], limit=3)
    if not focus_titles:
        return ""
    return "、".join(focus_titles)


def _risk_similarity(left: object, right: object) -> float:
    left_text = _normalize_text(f"{left.risk_description}{left.review_reasoning}")
    right_text = _normalize_text(f"{right.risk_description}{right.review_reasoning}")
    if not left_text or not right_text:
        return 0.0
    return SequenceMatcher(a=left_text, b=right_text).ratio()


def _should_merge_risk(representative: object, candidate: object) -> bool:
    if str(representative.rule_id) != str(candidate.rule_id):
        return False
    if str(representative.clause_id) == str(candidate.clause_id):
        return True
    if str(representative.location_label) == str(candidate.location_label):
        return True
    if extract_chapter_title(str(representative.location_label)) != extract_chapter_title(str(candidate.location_label)):
        return False
    return _risk_similarity(representative, candidate) >= 0.88


def _should_hide_group(group: dict[str, object], all_groups: list[dict[str, object]]) -> bool:
    unit_label = str(group.get("raw_unit_label") or "")
    rule_code = _normalize_rule_code(str(group.get("rule_id") or ""))
    if unit_label != "不确定审查对象" or rule_code != "R3":
        return False
    return any(
        _normalize_rule_code(str(other.get("rule_id") or "")) == "R3"
        and str(other.get("raw_unit_label") or "") != "不确定审查对象"
        for other in all_groups
    )


def _normalize_risk_title(*, rule_code: str, risk_title: str, unit_label: str, unit_name: str, evidence_text: str) -> str:
    title = str(risk_title).strip()
    if title:
        if rule_code == "R9" and "评分标准量化不足" in title:
            return "评分标准量化不足，自由裁量空间较大"
        if title not in GENERIC_RISK_TITLES.get(rule_code, set()):
            return title

    combined_text = "\n".join(
        part
        for part in (unit_label, unit_name, evidence_text)
        if str(part).strip()
    )
    if rule_code == "R12":
        if any(keyword in combined_text for keyword in ("财政", "据实支付", "初验款", "终验款", "付款", "支付")):
            return "付款条件与财政资金挂钩，存在回款责任失衡风险"
        if "单方解除" in combined_text and "不承担任何违约责任" in combined_text:
            return "单方解除且免责，存在合同责任失衡风险"
        if any(keyword in combined_text for keyword in ("检测", "验收", "费用承担")):
            return "检测或验收责任分配失衡，建议人工复核"
        return "合同条款存在责任失衡风险"
    if rule_code == "R9":
        return "评分标准量化不足，自由裁量空间较大"
    return title


def group_risks(
    *,
    risks: list[object],
    repository: object,
) -> list[dict[str, object]]:
    grouped: list[dict[str, object]] = []
    for risk in sort_risks_for_display(risks):
        bucket = next(
            (
                item
                for item in grouped
                if _should_merge_risk(item["representative"], risk)
            ),
            None,
        )
        if bucket is None:
            bucket = {
                "representative": risk,
                "risks": [],
                "evidences": [],
            }
            grouped.append(bucket)
        bucket["risks"].append(risk)
        bucket["evidences"].extend(repository.list_evidences_by_risk(risk.risk_id))

    groups: list[dict[str, object]] = []
    for bucket in grouped:
        representative = bucket["representative"]
        merged_risks = list(bucket["risks"])
        merged_evidences = list(bucket["evidences"])
        clause = repository.get_clause(representative.clause_id)
        chapter_title = (
            str(getattr(clause, "chapter_title", "")).strip()
            or extract_chapter_title(representative.location_label)
        )
        clause_type = (
            str(getattr(clause, "clause_type", "")).strip()
            or extract_clause_type(representative.review_reasoning)
        )
        raw_unit_label = (
            str(getattr(clause, "unit_label", "")).strip()
            or extract_unit_label(representative.review_reasoning)
            or "未标注"
        )
        unit_name = str(getattr(clause, "unit_name", "")).strip()
        unit_label = _format_unit_display(unit_label=raw_unit_label, unit_name=unit_name)
        location_label = (
            str(getattr(clause, "location_label", "")).strip()
            or str(representative.location_label)
        )
        evidence_text = merge_texts(
            [str(item.quoted_text) for item in merged_evidences],
            fallback="无",
        )
        risk_title = _normalize_risk_title(
            rule_code=_normalize_rule_code(representative.rule_id),
            risk_title=str(representative.risk_title),
            unit_label=raw_unit_label,
            unit_name=unit_name,
            evidence_text=evidence_text,
        )
        groups.append(
            {
                "risk_id": representative.risk_id,
                "risk_title": risk_title,
                "raw_risk_title": representative.risk_title,
                "risk_level": representative.risk_level,
                "rule_id": representative.rule_id,
                "rule_code": _normalize_rule_code(representative.rule_id),
                "rule_domain": representative.rule_domain,
                "location_label": _normalize_location_label(location_label),
                "chapter_title": _normalize_chapter_title(chapter_title),
                "clause_type": clause_type,
                "unit_label": unit_label,
                "raw_unit_label": raw_unit_label,
                "risk_description": merge_texts(
                    [str(item.risk_description) for item in merged_risks],
                    fallback=str(representative.risk_description),
                ),
                "review_reasoning": merge_texts(
                    [str(item.review_reasoning) for item in merged_risks],
                    fallback=str(representative.review_reasoning),
                ),
                "evidence_text": evidence_text,
                "evidence_note": merge_texts(
                    [str(item.evidence_note) for item in merged_evidences],
                    fallback="无",
                ),
                "merged_hit_count": len(merged_risks),
                "merged_risk_ids": [str(item.risk_id) for item in merged_risks],
                "created_at": representative.created_at,
            }
        )
    visible_groups = [group for group in groups if not _should_hide_group(group, groups)]
    return sorted(
        visible_groups,
        key=lambda item: (
            SEVERITY_ORDER.get(str(item["risk_level"]), 9),
            str(item["risk_title"]),
            str(item["chapter_title"]),
            str(item["created_at"]),
        ),
    )


def count_risk_groups(risk_groups: list[dict[str, object]]) -> dict[str, int]:
    summary = {"high": 0, "medium": 0, "low": 0}
    for group in risk_groups:
        level = str(group["risk_level"])
        if level == "高":
            summary["high"] += 1
        elif level == "中":
            summary["medium"] += 1
        elif level == "低":
            summary["low"] += 1
    return summary


def build_top_risk_payload(risk_group: dict[str, object]) -> dict[str, object]:
    return {
        "risk_id": risk_group["risk_id"],
        "risk_title": risk_group["risk_title"],
        "risk_level": risk_group["risk_level"],
        "rule_code": risk_group["rule_code"],
        "location_label": risk_group["location_label"],
        "chapter_title": risk_group["chapter_title"],
        "clause_type": risk_group["clause_type"],
        "unit_label": risk_group["unit_label"],
        "risk_description": risk_group["risk_description"],
        "review_reasoning": risk_group["review_reasoning"],
        "merged_hit_count": risk_group["merged_hit_count"],
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
        "page_guidance": "先看风险统计，再看重点风险摘要，最后查看完整结论和审查报告，会更容易把握重点。",
        "primary_actions": [
            {"label": "刷新当前结果页", "url": str(result_payload["page_url"])},
            {"label": "查看结果接口", "url": str(result_payload["result_api_url"])},
        ],
        "support_notes": [
            {
                "title": "查看提示",
                "body": "如果需要继续核对，可先从重点风险组摘要进入，再回到完整审查报告查看上下文。",
            },
            {
                "title": "联调说明",
                "body": "结果页主要消费结果接口、状态接口和下载地址。联调时应优先确认风险组统计与页面展示是否一致。",
            },
        ],
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
        "page_guidance": "建议先查看状态接口确认失败原因，再根据提示重新提交文件或重新触发任务。",
        "primary_actions": [
            {"label": "再次查看当前页面", "url": f"/review-tasks/{task_id}/page"},
        ],
        "support_notes": [
            {
                "title": "交付说明",
                "body": "失败态页面优先承担告知和排查入口，不承载复杂修复操作。",
            }
        ],
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
        "page_guidance": "系统仍在处理中。建议先查看状态接口确认当前阶段，再稍后刷新本页或轮询结果接口。",
        "primary_actions": [
            {"label": "刷新当前页面", "url": f"/review-tasks/{task_id}/page"},
            {"label": "查看状态接口", "url": f"/api/v1/review-tasks/{task_id}"},
        ],
        "support_notes": [
            {
                "title": "联调说明",
                "body": "审核中页面当前只负责提示进度和给出查看入口，不承担复杂交互。",
            }
        ],
    }
