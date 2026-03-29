from __future__ import annotations

import re
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
RULE_CODE_UNIT_LABEL_HINTS = {
    "R1": ("单条资格要求", "单条信用要求", "资格性审查表", "商务要求项"),
    "R2": ("单条资格要求", "单条资质要求", "资格性审查表"),
    "R3": ("单条资格要求", "单条业绩要求", "单条资质要求", "单条信用要求", "资格性审查表", "商务要求项"),
    "R4": ("单条业绩要求", "单个评分项", "商务分规则", "资格性审查表"),
    "R5": ("单条技术参数", "单个参数项", "单条功能要求", "单条服务要求", "单个偏离项", "商务要求项"),
    "R6": ("单条技术参数", "单个参数项", "单条功能要求", "单个偏离项"),
    "R7": ("单条技术参数", "单个参数项", "单条功能要求", "单条服务要求", "单条交付要求", "商务要求项"),
    "R8": ("单条技术参数", "单个参数项", "单条功能要求", "单条服务要求", "单条交付要求"),
    "R9": ("单个评分项", "价格分规则", "商务分规则", "技术分规则"),
    "R10": ("单个评分项", "价格分规则", "商务分规则", "技术分规则"),
    "R11": ("资格性审查表", "符合性审查表", "单个评分项", "价格分规则", "商务分规则", "技术分规则"),
    "R12": ("付款条款", "验收条款", "违约责任条款", "质保条款", "费用承担条款", "单条合同条款", "商务要求项"),
}
GENERIC_UNIT_LABELS = {"普通条款", "普通表格行", "不确定审查对象"}
SCORING_UNIT_LABELS = {"单个评分项", "价格分规则", "商务分规则", "技术分规则"}
SCORING_SIGNAL_KEYWORDS = (
    "评分",
    "评审",
    "打分",
    "得分",
    "分值",
    "量化",
    "综合评分",
    "综合评价",
    "优良中差",
    "主观",
    "酌情",
    "自由裁量",
    "裁量空间",
)
QUALIFICATION_UNIT_LABELS = {"单条资格要求", "单条业绩要求", "单条资质要求", "单条信用要求", "资格性审查表"}
QUALIFICATION_CERT_OR_CREDIT_KEYWORDS = (
    "高新技术企业",
    "科技型中小企业",
    "纳税信用a",
    "纳税信用 a",
    "信用等级a",
    "信用等级 a",
)
QUALIFICATION_REGION_OR_PERFORMANCE_KEYWORDS = (
    "深圳市",
    "本市",
    "当地",
    "同类项目业绩不少于",
    "类似项目业绩不少于",
    "业绩不少于",
)
SCORING_SCALE_KEYWORDS = ("资产总额", "从业人员", "纳税额", "营业收入")
SCORING_SUBJECTIVE_KEYWORDS = ("优良中差", "综合评价", "酌情", "美观", "体验", "友好", "主观")
SCORING_CERTIFICATE_KEYWORDS = ("许可证", "资格证", "证书", "认证", "测评师")
PRICE_RULE_KEYWORDS = ("价格分", "报价得分", "价格评审", "评标基准价", "基准价", "平均价", "算术平均")
YEAR_LIMIT_PATTERN = re.compile(r"(成立|设立|经营|注册).{0,8}(满|达到|不少于|超过)?\s*[0-9一二三四五六七八九十两]+\s*年")
PERFORMANCE_COUNT_PATTERN = re.compile(r"(同类项目|类似项目|业绩|案例).{0,20}(不少于|至少|达到|满)\s*[0-9一二三四五六七八九十两]+\s*(个|项|份|家)")
SCORING_CONTEXT_PATTERN = re.compile(r"(得\d+分|得分|满分|评分|分值)")
R5_NOISE_LOCATION_KEYWORDS = (
    "项目详细报价",
    "规格/型号",
    "知识产权",
    "商标权",
    "专利权",
    "工业设计权",
    "来货初验",
    "型号、外观、数量",
)
R5_NOISE_TEXT_KEYWORDS = (
    "仅填写规格信息",
    "不填型号信息",
    "定制",
    "侵犯知识产权",
    "商标权",
    "专利权",
    "工业设计权",
    "型号、外观、数量",
    "开箱验货",
)
R4_NOISE_LOCATION_KEYWORDS = (
    "信用信息",
    "信用记录",
    "信用承诺",
    "特别警示",
    "评审委员会",
    "评审活动",
    "投标及履约承诺函",
)
R4_BOILERPLATE_KEYWORDS = (
    "资格性审查表",
    "符合性审查表",
    "综合评分法",
    "评审方法",
    "评审定标",
    "评审活动",
    "重新评审",
    "独立评审",
    "评标因素",
)
SCORING_BOILERPLATE_KEYWORDS = (
    "综合评分法",
    "评审委员会",
    "评审活动",
    "评审定标",
    "候选中标人",
    "评标结果",
)


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
                available_rule_codes = set(rules_by_code)
                for finding in findings:
                    clause_id = str(finding.get("clause_id") or "").strip()
                    clause = clauses_by_id.get(clause_id)
                    rule_code = _normalize_finding_rule_code(
                        finding=finding,
                        clause=clause,
                        available_rule_codes=available_rule_codes,
                    )
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
        selected_rules = _select_rules_for_clause_batch(
            rules=runtime_input.rules,
            clause_batch=clause_batch,
            rule_limit=rule_limit,
            rule_candidate_map=rule_candidate_map,
        )
        heuristic_findings = _build_heuristic_findings(
            clause_batch=clause_batch,
            selected_rules=selected_rules,
        )
        try:
            llm_findings = self.client.review_batch(
                prompt_text=runtime_input.prompt_text,
                payload=_build_batch_payload(
                    selected_rules=selected_rules,
                    clause_batch=clause_batch,
                    clause_max_chars=clause_max_chars,
                ),
            )
            filtered_findings = [
                finding
                for finding in heuristic_findings + llm_findings
                if not _should_drop_finding_for_noise(
                    finding=finding,
                    clauses_by_id={str(getattr(item, "clause_id", "")): item for item in clause_batch},
                )
            ]
            return _dedupe_findings_by_clause_and_rule(filtered_findings)
        except LlmRequestError:
            if heuristic_findings and len(clause_batch) == 1:
                return heuristic_findings
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
    selected_rules: list[dict[str, object]],
    clause_batch: list[object],
    clause_max_chars: int,
) -> dict[str, object]:
    return {
        "rules": [
            _build_rule_payload(rule)
            for rule in selected_rules
        ],
        "clauses": [
            {
                "clause_id": clause.clause_id,
                "review_unit_id": clause.review_unit_id,
                "module_type": clause.module_type,
                "unit_type": clause.unit_type,
                "unit_label": clause.unit_label,
                "unit_name": clause.unit_name,
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
    score += _score_clause_explicit_priority(clause=clause)

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


def _score_clause_explicit_priority(*, clause: object) -> int:
    score = 0
    if _has_explicit_r4_signal(clause):
        score += 10
    clause_text = str(getattr(clause, "clause_text", "")).strip()
    normalized_text = _normalize_for_match(
        "\n".join(
            [
                str(getattr(clause, "chapter_title", "")),
                str(getattr(clause, "unit_name", "")),
                clause_text,
            ]
        )
    )
    if any(keyword in normalized_text for keyword in map(_normalize_for_match, QUALIFICATION_CERT_OR_CREDIT_KEYWORDS)):
        score += 8
    elif YEAR_LIMIT_PATTERN.search(clause_text):
        score += 7
    if any(keyword in clause_text for keyword in ("评标基准价", "算术平均价", "平均价")):
        score += 7
    return score


def _classify_clause_business_modules(clause: object) -> list[str]:
    module_type = str(getattr(clause, "module_type", "")).strip()
    if module_type and module_type != "其他":
        return [module_type]
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


def _preferred_unit_labels_for_rule(rule: dict[str, object]) -> tuple[str, ...]:
    rule_code = str(rule.get("rule_code") or "")
    return RULE_CODE_UNIT_LABEL_HINTS.get(rule_code, tuple())


def _score_rule_clause_match(
    *,
    rule: dict[str, object],
    clause: object,
    preferred_modules: set[str],
) -> int:
    rule_unit_labels = set(_preferred_unit_labels_for_rule(rule))
    rule_code = str(rule.get("rule_code") or "")
    score = 0
    clause_modules = set(_classify_clause_business_modules(clause))
    module_matched = bool(clause_modules & preferred_modules)
    if module_matched:
        score += 4
    unit_label = str(getattr(clause, "unit_label", "")).strip()
    if unit_label in rule_unit_labels:
        score += 4
    elif unit_label and unit_label not in GENERIC_UNIT_LABELS:
        score += 1
    elif unit_label in GENERIC_UNIT_LABELS:
        score -= 1
    clause_type = str(getattr(clause, "clause_type", ""))
    if clause_type == "条款片段":
        score += 2
    chapter_title = str(getattr(clause, "chapter_title", ""))
    if any(keyword in chapter_title for keyword in HIGH_VALUE_SECTION_KEYWORDS):
        score += 1
    if rule_code == "R5" and _is_r5_noise_clause(clause):
        return 0
    specific_signal_score = _score_rule_specific_signal(rule_code=rule_code, clause=clause)
    score += specific_signal_score
    text_matched = _rule_matches_batch_text(
        rule=rule,
        batch_text=f"{chapter_title}\n{getattr(clause, 'clause_text', '')}",
    )
    if text_matched:
        score += 5
    if not module_matched and not text_matched and specific_signal_score <= 0:
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


def _build_heuristic_findings(
    *,
    clause_batch: list[object],
    selected_rules: list[dict[str, object]],
) -> list[dict[str, object]]:
    available_rule_codes = {str(rule.get("rule_code") or "").strip() for rule in selected_rules}
    findings: list[dict[str, object]] = []
    for clause in clause_batch:
        findings.extend(_detect_qualification_gap_findings(clause=clause, available_rule_codes=available_rule_codes))
        findings.extend(_detect_scoring_gap_findings(clause=clause, available_rule_codes=available_rule_codes))
        findings.extend(_detect_price_rule_gap_findings(clause=clause, available_rule_codes=available_rule_codes))
    return _dedupe_findings_by_clause_and_rule(findings)


def _dedupe_findings_by_clause_and_rule(findings: list[dict[str, object]]) -> list[dict[str, object]]:
    deduped: list[dict[str, object]] = []
    seen_keys: set[tuple[str, str]] = set()
    for finding in findings:
        clause_id = str(finding.get("clause_id") or "").strip()
        rule_code = str(finding.get("rule_code") or "").strip()
        if not clause_id or not rule_code:
            continue
        key = (clause_id, rule_code)
        if key in seen_keys:
            continue
        seen_keys.add(key)
        deduped.append(finding)
    return deduped


def _should_drop_finding_for_noise(
    *,
    finding: dict[str, object],
    clauses_by_id: dict[str, object],
) -> bool:
    rule_code = str(finding.get("rule_code") or "").strip()
    clause_id = str(finding.get("clause_id") or "").strip()
    clause = clauses_by_id.get(clause_id)
    if rule_code == "R5" and clause is not None:
        return _is_r5_noise_clause(clause)
    if rule_code == "R4" and clause is not None:
        return _is_r4_noise_clause(clause) or _is_r4_boilerplate_clause(clause) or not _has_explicit_r4_signal(clause)
    return False


def _is_r5_noise_clause(clause: object) -> bool:
    location_label = str(getattr(clause, "location_label", "")).strip()
    chapter_title = str(getattr(clause, "chapter_title", "")).strip()
    unit_name = str(getattr(clause, "unit_name", "")).strip()
    clause_text = str(getattr(clause, "clause_text", "")).strip()
    combined_text = "\n".join([location_label, chapter_title, unit_name, clause_text])
    if any(keyword in combined_text for keyword in R5_NOISE_LOCATION_KEYWORDS):
        return True
    if any(keyword in clause_text for keyword in R5_NOISE_TEXT_KEYWORDS):
        return True
    if "型号" in clause_text and "同品牌" not in clause_text and "指定品牌" not in clause_text and "原厂" not in clause_text:
        if any(keyword in combined_text for keyword in ("验收", "报价", "承诺函", "知识产权")):
            return True
    return False


def _is_r4_noise_clause(clause: object) -> bool:
    location_label = str(getattr(clause, "location_label", "")).strip()
    chapter_title = str(getattr(clause, "chapter_title", "")).strip()
    unit_name = str(getattr(clause, "unit_name", "")).strip()
    clause_text = str(getattr(clause, "clause_text", "")).strip()
    combined_text = "\n".join([location_label, chapter_title, unit_name, clause_text])
    has_performance_signal = (
        bool(PERFORMANCE_COUNT_PATTERN.search(clause_text))
        or "同类项目" in clause_text
        or "类似项目" in clause_text
        or "业绩" in clause_text
        or "案例" in clause_text
    )
    if has_performance_signal:
        return False
    return any(keyword in combined_text for keyword in R4_NOISE_LOCATION_KEYWORDS)


def _has_explicit_r4_signal(clause: object) -> bool:
    clause_text = str(getattr(clause, "clause_text", "")).strip()
    combined_text = "\n".join(
        [
            str(getattr(clause, "location_label", "")).strip(),
            str(getattr(clause, "unit_name", "")).strip(),
            clause_text,
        ]
    )
    has_requirement_phrase = any(
        keyword in clause_text
        for keyword in ("投标人须", "须具备", "应具备", "须提供", "提供合同", "业绩要求")
    )
    has_region_signal = any(keyword in combined_text for keyword in ("深圳市", "本市", "当地"))
    has_performance_signal = any(keyword in combined_text for keyword in ("同类项目", "类似项目", "业绩", "案例"))
    has_count_signal = bool(PERFORMANCE_COUNT_PATTERN.search(clause_text))
    has_direct_phrase = any(
        keyword in combined_text
        for keyword in ("同类项目业绩不少于", "类似项目业绩不少于", "业绩不少于", "案例不少于")
    )
    return (has_count_signal and has_performance_signal) or has_direct_phrase or (
        has_requirement_phrase and has_region_signal and has_performance_signal
    )


def _is_r4_boilerplate_clause(clause: object) -> bool:
    if _has_explicit_r4_signal(clause):
        return False
    combined_text = "\n".join(
        [
            str(getattr(clause, "location_label", "")).strip(),
            str(getattr(clause, "chapter_title", "")).strip(),
            str(getattr(clause, "unit_name", "")).strip(),
            str(getattr(clause, "clause_text", "")).strip(),
        ]
    )
    return any(keyword in combined_text for keyword in R4_BOILERPLATE_KEYWORDS)


def _score_rule_specific_signal(*, rule_code: str, clause: object) -> int:
    clause_text = str(getattr(clause, "clause_text", "")).strip()
    normalized_text = _normalize_for_match(
        "\n".join(
            [
                str(getattr(clause, "location_label", "")),
                str(getattr(clause, "unit_name", "")),
                clause_text,
            ]
        )
    )
    if rule_code == "R3":
        if any(keyword in normalized_text for keyword in map(_normalize_for_match, QUALIFICATION_CERT_OR_CREDIT_KEYWORDS)):
            return 8
        if YEAR_LIMIT_PATTERN.search(clause_text):
            return 7
    if rule_code == "R4":
        if _is_r4_noise_clause(clause):
            return -6
        if _is_r4_boilerplate_clause(clause):
            return -5
        if _has_explicit_r4_signal(clause):
            return 10
        if PERFORMANCE_COUNT_PATTERN.search(clause_text):
            return 8
        if any(keyword in clause_text for keyword in QUALIFICATION_REGION_OR_PERFORMANCE_KEYWORDS):
            return 6
    if rule_code == "R9":
        if any(keyword in clause_text for keyword in ("评标基准价", "算术平均价", "平均价")):
            return 9
        if any(keyword in normalized_text for keyword in map(_normalize_for_match, SCORING_SCALE_KEYWORDS)):
            return 8
        if "成立时间" in clause_text or YEAR_LIMIT_PATTERN.search(clause_text):
            return 7
        if any(keyword in clause_text for keyword in SCORING_CERTIFICATE_KEYWORDS):
            return 7
        if any(keyword in clause_text for keyword in SCORING_SUBJECTIVE_KEYWORDS):
            return 6
        if any(keyword in clause_text for keyword in SCORING_BOILERPLATE_KEYWORDS):
            return -4
    return 0


def _detect_qualification_gap_findings(
    *,
    clause: object,
    available_rule_codes: set[str],
) -> list[dict[str, object]]:
    module_type = str(getattr(clause, "module_type", "")).strip()
    unit_label = str(getattr(clause, "unit_label", "")).strip()

    clause_text = str(getattr(clause, "clause_text", "")).strip()
    summary_text = _normalize_for_match(
        "\n".join(
            [
                str(getattr(clause, "chapter_title", "")),
                str(getattr(clause, "unit_name", "")),
                clause_text,
            ]
        )
    )
    explicit_r3_signal = (
        any(keyword in summary_text for keyword in map(_normalize_for_match, QUALIFICATION_CERT_OR_CREDIT_KEYWORDS))
        or bool(YEAR_LIMIT_PATTERN.search(clause_text))
    )
    explicit_r4_signal = (
        _has_explicit_r4_signal(clause)
    )
    if module_type != "资格条件" and unit_label not in QUALIFICATION_UNIT_LABELS and not explicit_r3_signal and not explicit_r4_signal:
        return []
    findings: list[dict[str, object]] = []
    if "R3" in available_rule_codes:
        if any(keyword in summary_text for keyword in map(_normalize_for_match, QUALIFICATION_CERT_OR_CREDIT_KEYWORDS)):
            findings.append(
                _build_heuristic_finding(
                    clause=clause,
                    rule_code="R3",
                    risk_title="资格条件设置无关资质或信用要求，存在违法限定风险",
                    risk_level="高",
                    risk_category="资格条件违法限定",
                    review_reasoning="条款在资格条件中要求与项目直接履约关联不强的证书、企业认定或信用等级，存在不当设置准入门槛风险。",
                    need_human_confirm=True,
                )
            )
        elif YEAR_LIMIT_PATTERN.search(clause_text):
            findings.append(
                _build_heuristic_finding(
                    clause=clause,
                    rule_code="R3",
                    risk_title="资格条件设置成立年限要求，存在违法限定风险",
                    risk_level="高",
                    risk_category="资格条件违法限定",
                    review_reasoning="条款直接把成立或经营年限作为资格门槛，容易形成与项目履约能力不直接对应的不当限制。",
                    need_human_confirm=True,
                )
            )

    if "R4" in available_rule_codes:
        if not _is_r4_noise_clause(clause) and _has_explicit_r4_signal(clause):
            findings.append(
                _build_heuristic_finding(
                    clause=clause,
                    rule_code="R4",
                    risk_title="资格业绩要求存在区域或数量定向风险",
                    risk_level="高",
                    risk_category="资格条件违法限定",
                    review_reasoning="条款把特定区域、行业或业绩数量直接设为准入要求，可能缩小潜在供应商范围。",
                    need_human_confirm=True,
                )
            )
    return findings


def _detect_scoring_gap_findings(
    *,
    clause: object,
    available_rule_codes: set[str],
) -> list[dict[str, object]]:
    module_type = str(getattr(clause, "module_type", "")).strip()
    unit_label = str(getattr(clause, "unit_label", "")).strip()
    if "R9" not in available_rule_codes:
        return []

    clause_text = str(getattr(clause, "clause_text", "")).strip()
    if not clause_text or not SCORING_CONTEXT_PATTERN.search(clause_text):
        return []

    normalized_text = _normalize_for_match(
        "\n".join(
            [
                str(getattr(clause, "chapter_title", "")),
                str(getattr(clause, "unit_name", "")),
                clause_text,
            ]
        )
    )
    explicit_signal = (
        any(keyword in normalized_text for keyword in map(_normalize_for_match, SCORING_SCALE_KEYWORDS))
        or "成立时间" in clause_text
        or bool(YEAR_LIMIT_PATTERN.search(clause_text))
        or any(keyword in clause_text for keyword in SCORING_CERTIFICATE_KEYWORDS)
        or any(keyword in clause_text for keyword in SCORING_SUBJECTIVE_KEYWORDS)
    )
    if module_type != "评分办法" and unit_label not in SCORING_UNIT_LABELS and not explicit_signal:
        return []
    if any(keyword in normalized_text for keyword in map(_normalize_for_match, SCORING_SCALE_KEYWORDS)):
        return [
            _build_heuristic_finding(
                clause=clause,
                rule_code="R9",
                risk_title="评分因素设置不当，存在以规模财务指标打分风险",
                risk_level="高",
                risk_category="评分因素合法性",
                review_reasoning="条款把资产规模、人员数量或纳税等规模财务指标直接作为评分依据，存在评分因素设置不当风险。",
                need_human_confirm=True,
            )
        ]
    if "成立时间" in clause_text or YEAR_LIMIT_PATTERN.search(clause_text):
        return [
            _build_heuristic_finding(
                clause=clause,
                rule_code="R9",
                risk_title="评分因素设置不当，存在以成立年限打分风险",
                risk_level="高",
                risk_category="评分因素合法性",
                review_reasoning="条款把成立或经营年限直接转换为得分条件，存在将不宜评分内容纳入评审因素的风险。",
                need_human_confirm=True,
            )
        ]
    if any(keyword in clause_text for keyword in SCORING_CERTIFICATE_KEYWORDS):
        return [
            _build_heuristic_finding(
                clause=clause,
                rule_code="R9",
                risk_title="评分因素设置不当，存在以无关证书资质打分风险",
                risk_level="高",
                risk_category="评分因素合法性",
                review_reasoning="条款把许可证、认证或其他证书直接作为评分依据，存在与采购标的不直接相关的评分因素风险。",
                need_human_confirm=True,
            )
        ]
    if any(keyword in clause_text for keyword in SCORING_SUBJECTIVE_KEYWORDS):
        return [
            _build_heuristic_finding(
                clause=clause,
                rule_code="R9",
                risk_title="评分标准量化不足，自由裁量空间较大",
                risk_level="高",
                risk_category="评分方法违法",
                review_reasoning="条款包含主观评价或审美体验类表述，但缺少稳定量化标准，评审尺度可复核性较弱。",
                need_human_confirm=True,
            )
        ]
    return []


def _detect_price_rule_gap_findings(
    *,
    clause: object,
    available_rule_codes: set[str],
) -> list[dict[str, object]]:
    module_type = str(getattr(clause, "module_type", "")).strip()
    unit_label = str(getattr(clause, "unit_label", "")).strip()
    if "R9" not in available_rule_codes:
        return []

    clause_text = str(getattr(clause, "clause_text", "")).strip()
    summary_text = "\n".join(
        [
            str(getattr(clause, "chapter_title", "")),
            str(getattr(clause, "unit_name", "")),
            clause_text,
        ]
    )
    if not any(keyword in summary_text for keyword in PRICE_RULE_KEYWORDS):
        return []
    if module_type != "评分办法" and unit_label != "价格分规则":
        if "评标基准价" not in clause_text and "算术平均价" not in clause_text and "平均价" not in clause_text:
            return []

    if any(keyword in clause_text for keyword in ("平均价", "算术平均", "平均报价", "评标基准价", "基准价")):
        return [
            _build_heuristic_finding(
                clause=clause,
                rule_code="R9",
                risk_title="价格分计算方法疑似不符合低价优先原则",
                risk_level="高",
                risk_category="价格分规则合法性",
                review_reasoning="条款使用平均价、基准价或接近中间价的计分思路，需重点复核是否偏离综合评分法下的低价优先原则。",
                need_human_confirm=True,
            )
        ]
    return []


def _build_heuristic_finding(
    *,
    clause: object,
    rule_code: str,
    risk_title: str,
    risk_level: str,
    risk_category: str,
    review_reasoning: str,
    need_human_confirm: bool,
) -> dict[str, object]:
    return {
        "clause_id": str(getattr(clause, "clause_id", "")),
        "rule_code": rule_code,
        "risk_title": risk_title,
        "risk_level": risk_level,
        "risk_category": risk_category,
        "evidence_text": str(getattr(clause, "clause_text", "")),
        "review_reasoning": review_reasoning,
        "need_human_confirm": need_human_confirm,
    }


def _normalize_text(value: object, *, fallback: str) -> str:
    text = str(value or "").strip()
    return text or fallback


def _normalize_risk_level(value: object, *, fallback: str) -> str:
    level = str(value or "").strip()
    if level in {"高", "中", "低"}:
        return level
    return fallback


def _normalize_finding_rule_code(
    *,
    finding: dict[str, object],
    clause: object | None,
    available_rule_codes: set[str],
) -> str:
    rule_code = str(finding.get("rule_code") or "").strip()
    if rule_code != "R12" or clause is None:
        return rule_code
    if "R9" not in available_rule_codes:
        return rule_code
    if not _looks_like_scoring_finding(finding=finding, clause=clause):
        return rule_code
    return "R9"


def _looks_like_scoring_finding(*, finding: dict[str, object], clause: object) -> bool:
    unit_label = str(getattr(clause, "unit_label", "")).strip()
    module_type = str(getattr(clause, "module_type", "")).strip()
    if module_type == "评分办法" or unit_label in SCORING_UNIT_LABELS:
        return True

    summary_text = "\n".join(
        part
        for part in (
            str(getattr(clause, "unit_name", "")),
            str(finding.get("risk_title") or ""),
        )
        if part
    )
    return any(keyword in summary_text for keyword in SCORING_SIGNAL_KEYWORDS)


def _normalize_bool(value: object) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y", "是"}


def _build_risk_description(*, rule: dict[str, object], clause: object, finding: dict[str, object]) -> str:
    risk_category = _normalize_text(finding.get("risk_category"), fallback="未分类")
    risk_title = _normalize_text(finding.get("risk_title"), fallback=str(rule["rule_name"]))
    reasoning = _normalize_text(finding.get("review_reasoning"), fallback="模型未返回额外说明。")
    return (
        f"{clause.chapter_title}的{clause.unit_label}疑似命中规则 {rule['rule_code']}（{risk_title}），"
        f"风险分类：{risk_category}。模型判断：{reasoning}"
    )


def _build_review_reasoning(*, rule: dict[str, object], clause: object, finding: dict[str, object]) -> str:
    risk_category = _normalize_text(finding.get("risk_category"), fallback="未分类")
    need_human_confirm = "是" if _normalize_bool(finding.get("need_human_confirm")) else "否"
    reasoning = _normalize_text(finding.get("review_reasoning"), fallback="模型未返回额外说明。")
    return (
        f"LLM 审查在“{clause.location_label}”识别到疑似风险，"
        f"当前内容属于{clause.chapter_title}的{clause.clause_type}，"
        f"业务单元：{clause.unit_label}"
        f"{f'（{clause.unit_name}）' if str(clause.unit_name).strip() else ''}，"
        f"对应规则 {rule['rule_code']}（{rule['rule_name']}），"
        f"风险分类：{risk_category}，建议人工确认：{need_human_confirm}。"
        f"模型理由：{reasoning}"
    )


def _build_evidence_note(*, clause: object, finding: dict[str, object]) -> str:
    risk_category = _normalize_text(finding.get("risk_category"), fallback="未分类")
    need_human_confirm = "是" if _normalize_bool(finding.get("need_human_confirm")) else "否"
    return (
        f"{clause.chapter_title}的{clause.unit_label}原文证据，"
        f"片段类型：{clause.clause_type}。"
        f"风险分类：{risk_category}，建议人工确认：{need_human_confirm}。"
    )
