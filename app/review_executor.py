from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.asset_loader import ReviewAssetLoader
from app.llm_client import LlmRequestError, OpenAiCompatibleLlmClient, load_llm_config_from_env
from app.models import build_evidence_item_record, build_risk_item_record
from app.repository import JsonRepository
from app.review_assembler import ReviewInputAssembler

MIN_RETRY_CLAUSE_MAX_CHARS = 300


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
            clauses_by_id = {
                clause.clause_id: clause
                for clause in runtime_input.clauses
            }
            total_findings = 0
            seen_keys: set[tuple[str, str, str]] = set()

            for clause_batch in _chunk_clauses_for_review(
                runtime_input.clauses,
                batch_size=self.client.batch_size,
                clause_max_chars=self.client.clause_max_chars,
                batch_char_budget=self.client.batch_char_budget,
            ):
                findings = self._review_clause_batch(
                    runtime_input=runtime_input,
                    clause_batch=clause_batch,
                    clause_max_chars=self.client.clause_max_chars,
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

            task.transition_to("aggregating", f"审查执行完成，已生成 {total_findings} 条中间审查结果，待结果汇总。")
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
    ) -> list[dict[str, object]]:
        try:
            return self.client.review_batch(
                prompt_text=runtime_input.prompt_text,
                payload=_build_batch_payload(
                    runtime_input=runtime_input,
                    clause_batch=clause_batch,
                    clause_max_chars=clause_max_chars,
                ),
            )
        except LlmRequestError:
            if len(clause_batch) > 1:
                midpoint = max(1, len(clause_batch) // 2)
                left_findings = self._review_clause_batch(
                    runtime_input=runtime_input,
                    clause_batch=clause_batch[:midpoint],
                    clause_max_chars=clause_max_chars,
                )
                right_findings = self._review_clause_batch(
                    runtime_input=runtime_input,
                    clause_batch=clause_batch[midpoint:],
                    clause_max_chars=clause_max_chars,
                )
                return left_findings + right_findings

            next_clause_max_chars = _next_retry_clause_max_chars(clause_max_chars)
            if next_clause_max_chars < clause_max_chars:
                return self._review_clause_batch(
                    runtime_input=runtime_input,
                    clause_batch=clause_batch,
                    clause_max_chars=next_clause_max_chars,
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


def _build_batch_payload(*, runtime_input: object, clause_batch: list[object], clause_max_chars: int) -> dict[str, object]:
    return {
        "task": {
            "task_id": runtime_input.task_id,
            "document_id": runtime_input.document_id,
            "file_name": runtime_input.file_name,
        },
        "rules": [
            dict(rule)
            for rule in runtime_input.rules
        ],
        "clauses": [
            {
                "clause_id": clause.clause_id,
                "chapter_title": clause.chapter_title,
                "clause_type": clause.clause_type,
                "location_label": clause.location_label,
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
            "严格参考规则对象中的命中定义、正例、反例和重点关注项。",
            "优先检查 R1、R3、R5、R9、R12 等高价值规则。",
            "遇到同品牌、原厂保修、厂家认证讲师、执业医师证、评分量化不足等高价值表述时优先判断。",
            "仅在证据足以支撑时输出 findings。",
            "没有命中时返回 {\"findings\":[]}。",
            "risk_level 只能填写 高、中、低。",
            "need_human_confirm 只能填写 true 或 false。",
            "evidence_text 必须来自给定条款原文。",
            "同一条款同一规则只输出一次，不要用近义理由重复输出。",
        ],
    }


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
