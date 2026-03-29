from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any
from urllib import error, request


class LlmConfigurationError(RuntimeError):
    pass


class LlmRequestError(RuntimeError):
    pass


class LlmResponseFormatError(RuntimeError):
    pass


@dataclass(frozen=True)
class LlmClientConfig:
    base_url: str
    api_key: str
    model: str
    timeout_seconds: float
    max_clauses: int
    max_clauses_per_rule: int
    batch_size: int
    rule_limit: int
    batch_char_budget: int
    clause_max_chars: int
    max_completion_tokens: int
    reasoning_effort: str
    disable_thinking: bool


def load_llm_config_from_env() -> LlmClientConfig:
    base_url = (os.environ.get("OPENAI_BASE_URL") or "").strip()
    api_key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    model = (os.environ.get("OPENAI_MODEL") or "").strip()
    missing = [
        name
        for name, value in (
            ("OPENAI_BASE_URL", base_url),
            ("OPENAI_API_KEY", api_key),
            ("OPENAI_MODEL", model),
        )
        if not value
    ]
    if missing:
        raise LlmConfigurationError(f"缺少 LLM 环境变量: {', '.join(missing)}")

    timeout_seconds = float(os.environ.get("OPENAI_TIMEOUT_SECONDS", "90"))
    max_clauses = max(20, int(os.environ.get("OPENAI_REVIEW_MAX_CLAUSES", "160")))
    max_clauses_per_rule = max(8, int(os.environ.get("OPENAI_REVIEW_MAX_CLAUSES_PER_RULE", "24")))
    batch_size = max(1, int(os.environ.get("OPENAI_REVIEW_BATCH_SIZE", "4")))
    rule_limit = max(3, int(os.environ.get("OPENAI_REVIEW_RULE_LIMIT", "6")))
    clause_max_chars = max(200, int(os.environ.get("OPENAI_REVIEW_CLAUSE_MAX_CHARS", "800")))
    default_batch_char_budget = max(clause_max_chars, min(batch_size * clause_max_chars, 1000))
    batch_char_budget = max(
        clause_max_chars,
        int(os.environ.get("OPENAI_REVIEW_BATCH_CHAR_BUDGET", str(default_batch_char_budget))),
    )
    max_completion_tokens = max(128, int(os.environ.get("OPENAI_MAX_COMPLETION_TOKENS", "512")))
    reasoning_effort = (os.environ.get("OPENAI_REASONING_EFFORT") or "low").strip() or "low"
    disable_thinking = (os.environ.get("OPENAI_DISABLE_THINKING") or "").strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }
    return LlmClientConfig(
        base_url=base_url.rstrip("/"),
        api_key=api_key,
        model=model,
        timeout_seconds=timeout_seconds,
        max_clauses=max_clauses,
        max_clauses_per_rule=max_clauses_per_rule,
        batch_size=batch_size,
        rule_limit=rule_limit,
        batch_char_budget=batch_char_budget,
        clause_max_chars=clause_max_chars,
        max_completion_tokens=max_completion_tokens,
        reasoning_effort=reasoning_effort,
        disable_thinking=disable_thinking,
    )


class OpenAiCompatibleLlmClient:
    def __init__(self, config: LlmClientConfig):
        self.config = config

    @property
    def batch_size(self) -> int:
        return self.config.batch_size

    @property
    def max_clauses(self) -> int:
        return self.config.max_clauses

    @property
    def max_clauses_per_rule(self) -> int:
        return self.config.max_clauses_per_rule

    @property
    def clause_max_chars(self) -> int:
        return self.config.clause_max_chars

    @property
    def rule_limit(self) -> int:
        return self.config.rule_limit

    @property
    def batch_char_budget(self) -> int:
        return self.config.batch_char_budget

    def review_batch(self, *, prompt_text: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
        endpoint = f"{self.config.base_url}/chat/completions"
        body = {
            "model": self.config.model,
            "temperature": 0,
            "max_completion_tokens": self.config.max_completion_tokens,
            "reasoning_effort": self.config.reasoning_effort,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        f"{prompt_text}\n\n"
                        "你必须只输出 JSON 对象，不要输出额外解释、Markdown 标记或代码块。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        "请基于以下输入执行结构化审查，并仅输出形如 "
                        '{"findings":[...]} 的 JSON。\n'
                        f"{json.dumps(payload, ensure_ascii=False, separators=(',', ':'))}"
                    ),
                },
            ],
        }
        if self.config.disable_thinking:
            body["max_tokens"] = self.config.max_completion_tokens
            body["chat_template_kwargs"] = {"enable_thinking": False}
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        http_request = request.Request(
            endpoint,
            data=data,
            method="POST",
            headers={
                "Content-Type": "application/json; charset=utf-8",
                "Authorization": f"Bearer {self.config.api_key}",
            },
        )
        try:
            with request.urlopen(http_request, timeout=self.config.timeout_seconds) as response:
                response_payload = json.loads(response.read().decode("utf-8"))
        except error.HTTPError as exc:
            detail = exc.read().decode("utf-8", errors="ignore")
            raise LlmRequestError(f"LLM 调用失败，HTTP {exc.code}: {detail}") from exc
        except error.URLError as exc:
            raise LlmRequestError(f"LLM 服务不可达: {exc}") from exc
        except TimeoutError as exc:
            raise LlmRequestError("LLM 调用超时。") from exc

        content = _extract_message_content(response_payload)
        parsed = _parse_json_content(content)
        findings = parsed.get("findings", [])
        if not isinstance(findings, list):
            raise LlmResponseFormatError("LLM 输出缺少 findings 数组。")
        normalized: list[dict[str, Any]] = []
        for item in findings:
            if isinstance(item, dict):
                normalized.append(item)
        return normalized


def _extract_message_content(response_payload: dict[str, Any]) -> str:
    choices = response_payload.get("choices")
    if not isinstance(choices, list) or not choices:
        raise LlmResponseFormatError("LLM 响应缺少 choices。")
    message = choices[0].get("message")
    if not isinstance(message, dict):
        raise LlmResponseFormatError("LLM 响应缺少 message。")
    candidates = [
        _extract_text_from_value(message.get("content")),
        _extract_text_from_value(message.get("reasoning")),
    ]
    for candidate in candidates:
        if candidate:
            return candidate
    raise LlmResponseFormatError("LLM 响应缺少可解析文本内容。")


def _extract_text_from_value(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        text_parts = [
            str(item.get("text"))
            for item in value
            if isinstance(item, dict) and item.get("type") == "text" and item.get("text")
        ]
        if text_parts:
            return "\n".join(text_parts)
    if isinstance(value, dict):
        for key in ("text", "content", "reasoning"):
            nested = value.get(key)
            if isinstance(nested, str) and nested:
                return nested
    return ""


def _parse_json_content(content: str) -> dict[str, Any]:
    candidate = content.strip()
    if candidate.startswith("```"):
        candidate = _strip_code_fence(candidate)
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        parsed = _parse_embedded_json_object(candidate)
    if not isinstance(parsed, dict):
        raise LlmResponseFormatError("LLM 输出根对象必须是 JSON 对象。")
    return parsed


def _strip_code_fence(content: str) -> str:
    lines = content.splitlines()
    if len(lines) >= 2 and lines[0].startswith("```") and lines[-1].startswith("```"):
        return "\n".join(lines[1:-1]).strip()
    return content


def _parse_embedded_json_object(candidate: str) -> dict[str, Any]:
    brace_positions = [index for index, char in enumerate(candidate) if char == "{"]
    best_match: dict[str, Any] | None = None
    best_span = -1
    for start in brace_positions:
        end = candidate.rfind("}")
        while end != -1:
            snippet = candidate[start : end + 1]
            try:
                parsed = json.loads(snippet)
            except json.JSONDecodeError:
                end = candidate.rfind("}", start, end)
                continue
            if isinstance(parsed, dict):
                span = end - start
                if span > best_span:
                    best_match = parsed
                    best_span = span
            end = candidate.rfind("}", start, end)
    if best_match is not None:
        return best_match
    raise LlmResponseFormatError("LLM 输出不是有效 JSON。")
