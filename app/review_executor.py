from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.asset_loader import ReviewAssetLoader
from app.llm_client import LlmRequestError, OpenAiCompatibleLlmClient, load_llm_config_from_env
from app.models import build_evidence_item_record, build_risk_item_record
from app.repository import JsonRepository
from app.review_assembler import ReviewInputAssembler

MIN_RETRY_CLAUSE_MAX_CHARS = 300
HIGH_PRIORITY_RULE_CODES = {"R1", "R3", "R5", "R9", "R12"}
HIGH_VALUE_SECTION_KEYWORDS = (
    "资格",
    "评分",
    "评审",
    "技术",
    "参数",
    "商务",
    "偏离",
    "合同",
    "服务",
)
BUSINESS_MODULE_KEYWORDS = {
    "资格条件": ("资格", "资质", "供应商资格", "证书", "业绩", "注册", "办公"),
    "采购需求": ("采购需求", "需求", "技术", "参数", "规格", "功能", "配置", "性能"),
    "评分办法": ("评分", "评审", "打分", "分值", "商务分", "技术分", "价格分", "量化"),
    "合同条款": ("合同", "付款", "违约", "验收", "履约", "质保"),
    "程序条款": ("投标", "开标", "评标", "定标", "废标", "澄清", "质疑", "投诉", "公告", "程序"),
    "政策条款": ("中小企业", "节能", "环保", "绿色", "进口产品", "政策"),
}
RULE_DOMAIN_MODULE_MAP = {
    "合法性规则": ("资格条件", "程序条款", "评分办法", "合同条款"),
    "公平竞争规则": ("资格条件", "采购需求", "评分办法"),
    "需求合理性规则": ("采购需求", "合同条款"),
    "评审可解释性规则": ("评分办法", "资格条件"),
    "合同与履约风险规则": ("合同条款", "采购需求"),
    "合同与程序风险规则": ("合同条款", "程序条款"),
    "程序与公开规则": ("程序条款",),
    "政策功能规则": ("政策条款", "采购需求", "评分办法"),
}
RULE_CODE_MODULE_MAP = {
    "R1": ("资格条件", "程序条款"),
    "R2": ("资格条件", "评分办法"),
    "R3": ("资格条件",),
    "R4": ("资格条件", "评分办法"),
    "R5": ("采购需求", "资格条件"),
    "R6": ("采购需求",),
    "R7": ("采购需求", "合同条款"),
    "R8": ("采购需求",),
    "R9": ("评分办法",),
    "R10": ("评分办法",),
    "R11": ("评分办法", "资格条件"),
    "R12": ("合同条款", "程序条款"),
}


class ReviewExecutor:
    def __init__(self, repository: JsonRepository, root_dir: Path):
        self.repository = repository
        self.assembler = ReviewInputAssembler(repository, ReviewAssetLoader(root_dir))
        self.client = OpenAiCompatibleLlmClient(load_llm_config_from_env())

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
            rules_by_code = {
                str(rule["rule_code"]): rule
                for rule in runtime_input.rules
            }
            rule_candidate_map = _select_rule_candidate_clause_map(
                rules=runtime_input.rules,
                clauses=runtime_input.clauses,
                max_clauses_per_rule=getattr(self.client, "max_clauses_per_rule", 24),
            )
            candidate_clauses = _select_candidate_clauses(
                clauses=runtime_input.clauses,
                rules=runtime_input.rules,
                rule_candidate_map=rule_candidate_map,
                max_clauses=getattr(self.client, "max_clauses", len(runtime_input.clauses)),
            )
            clauses_by_id = {
                clause.clause_id: clause
                for clause in candidate_clauses
            }
            total_findings = 0
            seen_keys: set[tuple[str, str, str]] = set()

            for clause_batch in _chunk_clauses_for_review(
                candidate_clauses,
                batch_size=self.client.batch_size,
                clause_max_chars=self.client.clause_max_chars,
                batch_char_budget=self.client.batch_char_budget,
            ):
                rule_limit = getattr(self.client, "rule_limit", len(runtime_input.rules))
                findings = self._review_clause_batch(
                    runtime_input=runtime_input,
                    clause_batch=clause_batch,
                    clause_max_chars=self.client.clause_max_chars,
                    rule_limit=rule_limit,
                    rule_candidate_map=rule_candidate_map,
                )
                for finding in findings:
                    clause_id = str(finding.get("clause_id") or "").strip()
                    rule_code = str(finding.get("rule_code") or "").strip()
                    clause = clauses_by_id.get(clause_id)
                    rule = rules_by_code.get(rule_code)
                    if clause is None or rule is None:
                        continue

                    evidence_text = _normalize_text(
                        finding.get("evidence_text"),
                        fallback=clause.clause_text,
                    )
                    dedupe_key = (clause.clause_id, rule_code, evidence_text)
                    if dedupe_key in seen_keys:
                        continue
                    seen_keys.add(dedupe_key)

                    total_findings += 1
                    risk_id = f"risk_{uuid4().hex[:12]}"
                    evidence_id = f"evidence_{uuid4().hex[:12]}"
                    risk = build_risk_item_record(
                        risk_id=risk_id,
                        task_id=task.task_id,
                        project_id=task.project_id,
                        document_id=task.document_id,
                        clause_id=clause.clause_id,
                        rule=rule,
                        location_label=clause.location_label,
                        risk_title=_normalize_text(finding.get("risk_title"), fallback=str(rule["rule_name"])),
                        risk_level=_normalize_risk_level(
                            finding.get("risk_level"),
                            fallback=str(rule["risk_level"]),
                        ),
                        risk_description=_build_risk_description(
                            rule=rule,
                            clause=clause,
                            finding=finding,
                        ),
                        review_reasoning=_build_review_reasoning(
                            rule=rule,
                            clause=clause,
                            finding=finding,
                        ),
                    )
                    evidence = build_evidence_item_record(
                        evidence_id=evidence_id,
                        risk_id=risk_id,
                        document_id=task.document_id,
                        clause_id=clause.clause_id,
                        quoted_text=evidence_text,
                        location_label=clause.location_label,
                        evidence_note=_build_evidence_note(clause=clause, finding=finding),
                    )
                    self.repository.save_risk(risk)
                    self.repository.save_evidence(evidence)

            task.transition_to(
                "aggregating",
                (
                    f"审查执行完成，候选片段 {len(candidate_clauses)}/{len(runtime_input.clauses)}，"
                    f"已生成 {total_findings} 条中间审查结果，待结果汇总。"
                ),
            )
            self.repository.save_task(task)
            self.repository.enqueue_result_job(task)
        except Exception as exc:
            task.mark_failed(
                error_code="REVIEW_EXECUTION_FAILED",
                error_message=str(exc),
                status_message="审查执行失败，请检查 LLM 配置或服务可用性。",
            )
            self.repository.save_task(task)
        finally:
            self.repository.delete_review_job(job_path)

    def _review_clause_batch(
        self,
        *,
        runtime_input: object,
        clause_batch: list[object],
        clause_max_chars: int,
        rule_limit: int,
        rule_candidate_map: dict[str, list[object]],
    ) -> list[dict[str, object]]:
        try:
            return self.client.review_batch(
                prompt_text=runtime_input.prompt_text,
                payload=_build_batch_payload(
                    runtime_input=runtime_input,
                    clause_batch=clause_batch,
                    clause_max_chars=clause_max_chars,
                    rule_limit=rule_limit,
                    rule_candidate_map=rule_candidate_map,
                ),
            )
        except LlmRequestError:
            if len(clause_batch) > 1:
                midpoint = max(1, len(clause_batch) // 2)
                left_findings = self._review_clause_batch(
                    runtime_input=runtime_input,
                    clause_batch=clause_batch[:midpoint],
                    clause_max_chars=clause_max_chars,
                    rule_limit=rule_limit,
                    rule_candidate_map=rule_candidate_map,
                )
                right_findings = self._review_clause_batch(
                    runtime_input=runtime_input,
                    clause_batch=clause_batch[midpoint:],
                    clause_max_chars=clause_max_chars,
                    rule_limit=rule_limit,
                    rule_candidate_map=rule_candidate_map,
                )
                return left_findings + right_findings

            next_clause_max_chars = _next_retry_clause_max_chars(clause_max_chars)
            if next_clause_max_chars < clause_max_chars:
                return self._review_clause_batch(
                    runtime_input=runtime_input,
                    clause_batch=clause_batch,
                    clause_max_chars=next_clause_max_chars,
                    rule_limit=rule_limit,
                    rule_candidate_map=rule_candidate_map,
                )
            raise


def _chunk_clauses(clauses: list[object], batch_size: int) -> list[list[object]]:
    return [
        clauses[index : index + batch_size]
        for index in range(0, len(clauses), batch_size)
    ]


def _chunk_clauses_for_review(
    clauses: list[object],
    *,
    batch_size: int,
    clause_max_chars: int,
    batch_char_budget: int,
) -> list[list[object]]:
    if not clauses:
        return []

    chunks: list[list[object]] = []
    current_chunk: list[object] = []
    current_char_total = 0
    effective_char_budget = max(clause_max_chars, batch_char_budget)
    for clause in clauses:
        clause_char_count = min(len(clause.clause_text), clause_max_chars)
        if current_chunk and (
            len(current_chunk) >= batch_size
            or current_char_total + clause_char_count > effective_char_budget
        ):
            chunks.append(current_chunk)
            current_chunk = []
            current_char_total = 0
        current_chunk.append(clause)
        current_char_total += clause_char_count

    if current_chunk:
        chunks.append(current_chunk)
    return chunks


def _next_retry_clause_max_chars(clause_max_chars: int) -> int:
    if clause_max_chars <= MIN_RETRY_CLAUSE_MAX_CHARS:
        return clause_max_chars
    return max(MIN_RETRY_CLAUSE_MAX_CHARS, clause_max_chars // 2)


def _build_batch_payload(
    *,
    runtime_input: object,
    clause_batch: list[object],
    clause_max_chars: int,
    rule_limit: int,
    rule_candidate_map: dict[str, list[object]],
) -> dict[str, object]:
    selected_rules = _select_rules_for_clause_batch(
        rules=runtime_input.rules,
        clause_batch=clause_batch,
        rule_limit=rule_limit,
        rule_candidate_map=rule_candidate_map,
    )
    return {
        "rules": [
            _build_rule_payload(rule)
            for rule in selected_rules
        ],
        "clauses": [
            {
                "clause_id": clause.clause_id,
                "chapter_title": clause.chapter_title,
                "clause_type": clause.clause_type,
                "clause_text": clause.clause_text[:clause_max_chars],
            }
            for clause in clause_batch
        ],
        "output_schema": {
            "root": "findings",
            "finding_fields": [
                "clause_id",
                "rule_code",
                "risk_title",
                "risk_level",
                "risk_category",
                "evidence_text",
                "review_reasoning",
                "need_human_confirm",
            ],
        },
        "review_requirements": [
            "只基于当前批次条款和给定规则做片段级判断。",
            "优先检查 R1、R3、R5、R9、R12 等高价值规则。",
            "仅在证据足以支撑时输出 findings。",
            "没有命中时返回 {\"findings\":[]}。",
            "risk_level 只能填写 高、中、低。",
            "need_human_confirm 只能填写 true 或 false。",
            "evidence_text 必须来自给定条款原文。",
            "同一条款同一规则只输出一次，不要用近义理由重复输出。",
        ],
    }


def _select_rule_candidate_clause_map(
    *,
    rules: list[dict[str, object]],
    clauses: list[object],
    max_clauses_per_rule: int,
) -> dict[str, list[object]]:
    rule_candidate_map: dict[str, list[object]] = {}
    for rule in rules:
        rule_code = str(rule.get("rule_code") or "")
        if not rule_code:
            continue
        scored: list[tuple[int, int, object]] = []
        preferred_modules = set(_preferred_modules_for_rule(rule))
        for clause in clauses:
            score = _score_rule_clause_match(
                rule=rule,
                clause=clause,
                preferred_modules=preferred_modules,
            )
            if score <= 0:
                continue
            scored.append((score, int(getattr(clause, "clause_order", 0)), clause))
        scored.sort(key=lambda item: (-item[0], item[1]))
        rule_candidate_map[rule_code] = [item[2] for item in scored[:max_clauses_per_rule]]
    return rule_candidate_map


def _select_candidate_clauses(
    *,
    clauses: list[object],
    rules: list[dict[str, object]],
    rule_candidate_map: dict[str, list[object]],
    max_clauses: int,
) -> list[object]:
    if len(clauses) <= max_clauses:
        return list(clauses)

    preferred_clause_ids = {
        clause.clause_id
        for candidate_clauses in rule_candidate_map.values()
        for clause in candidate_clauses
    }
    scored: list[tuple[int, int, object]] = []
    for clause in clauses:
        score = _score_clause_candidate(
            clause=clause,
            rules=rules,
            preferred_clause_ids=preferred_clause_ids,
        )
        scored.append((score, int(getattr(clause, "clause_order", 0)), clause))

    prioritized = sorted(
        scored,
        key=lambda item: (-item[0], item[1]),
    )
    selected = [item[2] for item in prioritized[:max_clauses]]
    return sorted(selected, key=lambda clause: int(getattr(clause, "clause_order", 0)))


def _score_clause_candidate(
    *,
    clause: object,
    rules: list[dict[str, object]],
    preferred_clause_ids: set[str],
) -> int:
    score = 0
    chapter_title = str(getattr(clause, "chapter_title", ""))
    clause_type = str(getattr(clause, "clause_type", ""))
    clause_text = str(getattr(clause, "clause_text", ""))
    combined_text = f"{chapter_title}\n{clause_text}"
    clause_id = str(getattr(clause, "clause_id", ""))
    modules = set(_classify_clause_business_modules(clause))

    if clause_type == "条款片段":
        score += 2
    if any(keyword in chapter_title for keyword in HIGH_VALUE_SECTION_KEYWORDS):
        score += 3
    score += min(len(modules), 2)
    if clause_id in preferred_clause_ids:
        score += 4

    matched_high_priority = 0
    matched_normal_priority = 0
    for rule in rules:
        if not _rule_matches_batch_text(rule=rule, batch_text=combined_text):
            continue
        rule_code = str(rule.get("rule_code") or "")
        if rule_code in HIGH_PRIORITY_RULE_CODES:
            matched_high_priority += 1
        else:
            matched_normal_priority += 1

    score += min(matched_high_priority, 3) * 3
    score += min(matched_normal_priority, 3)

    text_length = len(clause_text.strip())
    if 40 <= text_length <= 800:
        score += 1
    return score


def _classify_clause_business_modules(clause: object) -> list[str]:
    chapter_title = str(getattr(clause, "chapter_title", ""))
    clause_text = str(getattr(clause, "clause_text", ""))
    combined_text = f"{chapter_title}\n{clause_text}"
    modules: list[str] = []
    for module_name, keywords in BUSINESS_MODULE_KEYWORDS.items():
        if any(keyword in combined_text for keyword in keywords):
            modules.append(module_name)
    if not modules:
        modules.append("其他")
    return modules


def _preferred_modules_for_rule(rule: dict[str, object]) -> tuple[str, ...]:
    rule_code = str(rule.get("rule_code") or "")
    if rule_code in RULE_CODE_MODULE_MAP:
        return RULE_CODE_MODULE_MAP[rule_code]
    rule_domain = str(rule.get("rule_domain") or "")
    return RULE_DOMAIN_MODULE_MAP.get(rule_domain, ("采购需求", "资格条件", "评分办法"))


def _score_rule_clause_match(
    *,
    rule: dict[str, object],
    clause: object,
    preferred_modules: set[str],
) -> int:
    score = 0
    clause_modules = set(_classify_clause_business_modules(clause))
    module_matched = bool(clause_modules & preferred_modules)
    if module_matched:
        score += 4
    clause_type = str(getattr(clause, "clause_type", ""))
    if clause_type == "条款片段":
        score += 2
    chapter_title = str(getattr(clause, "chapter_title", ""))
    if any(keyword in chapter_title for keyword in HIGH_VALUE_SECTION_KEYWORDS):
        score += 1
    text_matched = _rule_matches_batch_text(
        rule=rule,
        batch_text=f"{chapter_title}\n{getattr(clause, 'clause_text', '')}",
    )
    if text_matched:
        score += 5
    if not module_matched and not text_matched:
        return 0
    return score


def _select_rules_for_clause_batch(
    *,
    rules: list[dict[str, object]],
    clause_batch: list[object],
    rule_limit: int,
    rule_candidate_map: dict[str, list[object]],
) -> list[dict[str, object]]:
    if len(rules) <= rule_limit:
        return list(rules)

    batch_text = "\n".join(str(clause.clause_text) for clause in clause_batch)
    batch_clause_ids = {
        str(getattr(clause, "clause_id", ""))
        for clause in clause_batch
    }
    selected: list[dict[str, object]] = []
    selected_codes: set[str] = set()

    for rule in rules:
        rule_code = str(rule.get("rule_code") or "")
        if rule_code in HIGH_PRIORITY_RULE_CODES:
            if not _rule_has_batch_candidates(
                rule_code=rule_code,
                rule_candidate_map=rule_candidate_map,
                batch_clause_ids=batch_clause_ids,
            ):
                continue
            selected.append(rule)
            selected_codes.add(rule_code)

    for rule in rules:
        rule_code = str(rule.get("rule_code") or "")
        if rule_code in selected_codes:
            continue
        if not _rule_has_batch_candidates(
            rule_code=rule_code,
            rule_candidate_map=rule_candidate_map,
            batch_clause_ids=batch_clause_ids,
        ):
            continue
        if _rule_matches_batch_text(rule=rule, batch_text=batch_text):
            selected.append(rule)
            selected_codes.add(rule_code)
        if len(selected) >= rule_limit:
            return selected[:rule_limit]

    for rule in rules:
        rule_code = str(rule.get("rule_code") or "")
        if rule_code in selected_codes:
            continue
        if not _rule_has_batch_candidates(
            rule_code=rule_code,
            rule_candidate_map=rule_candidate_map,
            batch_clause_ids=batch_clause_ids,
        ):
            continue
        selected.append(rule)
        selected_codes.add(rule_code)
        if len(selected) >= rule_limit:
            break

    return selected[:rule_limit]


def _rule_has_batch_candidates(
    *,
    rule_code: str,
    rule_candidate_map: dict[str, list[object]],
    batch_clause_ids: set[str],
) -> bool:
    candidate_ids = {
        str(getattr(clause, "clause_id", ""))
        for clause in rule_candidate_map.get(rule_code, [])
    }
    if not candidate_ids:
        return False
    return bool(candidate_ids & batch_clause_ids)


def _rule_matches_batch_text(*, rule: dict[str, object], batch_text: str) -> bool:
    normalized_text = _normalize_for_match(batch_text)
    if not normalized_text:
        return False

    for candidate in _iter_rule_match_terms(rule):
        normalized_candidate = _normalize_for_match(candidate)
        if len(normalized_candidate) < 2:
            continue
        if normalized_candidate in normalized_text:
            return True
    return False


def _iter_rule_match_terms(rule: dict[str, object]) -> list[str]:
    terms: list[str] = []
    for key in ("rule_name", "priority_hint", "hit_definition", "review_focus"):
        value = rule.get(key)
        if isinstance(value, str):
            terms.extend(_split_match_terms(value))
    for key in ("focus_terms", "positive_examples"):
        value = rule.get(key)
        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    terms.extend(_split_match_terms(item))
    return terms


def _split_match_terms(text: str) -> list[str]:
    normalized = str(text).replace("；", " ").replace("，", " ").replace("。", " ")
    normalized = normalized.replace("、", " ").replace("/", " ").replace("（", " ").replace("）", " ")
    normalized = normalized.replace("(", " ").replace(")", " ").replace("：", " ").replace(":", " ")
    return [part.strip() for part in normalized.split() if part.strip()]


def _normalize_for_match(text: str) -> str:
    return "".join(str(text).lower().split())


def _build_rule_payload(rule: dict[str, object]) -> dict[str, object]:
    return {
        "rule_code": rule.get("rule_code"),
        "rule_name": rule.get("rule_name"),
        "risk_level": rule.get("risk_level"),
        "execution_level": rule.get("execution_level"),
        "priority_hint": rule.get("priority_hint"),
        "hit_definition": rule.get("hit_definition"),
        "focus_terms": _trim_string_list(rule.get("focus_terms"), limit=6),
        "positive_examples": _trim_string_list(rule.get("positive_examples"), limit=2),
    }


def _trim_string_list(value: object, *, limit: int) -> list[str]:
    if not isinstance(value, list):
        return []
    items = [str(item).strip() for item in value if str(item).strip()]
    return items[:limit]


def _normalize_text(value: object, *, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _normalize_risk_level(value: object, *, fallback: str) -> str:
    level = str(value or "").strip()
    if level in {"高", "中", "低"}:
        return level
    return fallback


def _normalize_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y", "是"}


def _build_risk_description(*, rule: dict[str, object], clause: object, finding: dict[str, object]) -> str:
    risk_category = _normalize_text(finding.get("risk_category"), fallback="未分类")
    risk_title = _normalize_text(finding.get("risk_title"), fallback=str(rule["rule_name"]))
    reasoning = _normalize_text(finding.get("review_reasoning"), fallback="模型未返回额外说明。")
    return (
        f"{clause.chapter_title}的{clause.clause_type}疑似命中规则 {rule['rule_code']}（{risk_title}），"
        f"风险分类：{risk_category}。模型判断：{reasoning}"
    )


def _build_review_reasoning(*, rule: dict[str, object], clause: object, finding: dict[str, object]) -> str:
    risk_category = _normalize_text(finding.get("risk_category"), fallback="未分类")
    need_human_confirm = "是" if _normalize_bool(finding.get("need_human_confirm")) else "否"
    reasoning = _normalize_text(finding.get("review_reasoning"), fallback="模型未返回额外说明。")
    return (
        f"LLM 审查在“{clause.location_label}”识别到疑似风险，"
        f"当前内容属于{clause.chapter_title}的{clause.clause_type}，"
        f"对应规则 {rule['rule_code']}（{rule['rule_name']}），"
        f"风险分类：{risk_category}，建议人工确认：{need_human_confirm}。"
        f"模型理由：{reasoning}"
    )


def _build_evidence_note(*, clause: object, finding: dict[str, object]) -> str:
    risk_category = _normalize_text(finding.get("risk_category"), fallback="未分类")
    need_human_confirm = "是" if _normalize_bool(finding.get("need_human_confirm")) else "否"
    return (
        f"{clause.chapter_title}的{clause.clause_type}原文证据。"
        f"风险分类：{risk_category}，建议人工确认：{need_human_confirm}。"
    )
