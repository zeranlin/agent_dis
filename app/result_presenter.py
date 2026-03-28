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
