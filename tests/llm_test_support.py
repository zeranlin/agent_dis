from __future__ import annotations

import json
import os
import threading
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


class _FakeLlmHandler(BaseHTTPRequestHandler):
    server_version = "fake-llm/0.1"

    def do_POST(self) -> None:
        if self.path != "/v1/chat/completions":
            self.send_response(404)
            self.end_headers()
            return

        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        request_payload = json.loads(body.decode("utf-8"))
        findings = _build_findings_from_request(request_payload)
        response_payload = {
            "id": "chatcmpl-test",
            "object": "chat.completion",
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": json.dumps({"findings": findings}, ensure_ascii=False),
                    },
                    "finish_reason": "stop",
                }
            ],
        }
        response_body = json.dumps(response_payload, ensure_ascii=False).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(response_body)))
        self.end_headers()
        self.wfile.write(response_body)

    def log_message(self, format: str, *args: object) -> None:
        return


def _build_findings_from_request(request_payload: dict[str, object]) -> list[dict[str, object]]:
    messages = request_payload.get("messages", [])
    if not isinstance(messages, list):
        return []
    user_message = next(
        (
            item.get("content")
            for item in messages
            if isinstance(item, dict) and item.get("role") == "user"
        ),
        "",
    )
    if not isinstance(user_message, str):
        return []
    payload = _extract_embedded_json(user_message)
    clauses = payload.get("clauses", [])
    if not isinstance(clauses, list):
        return []

    findings: list[dict[str, object]] = []
    for clause in clauses:
        if not isinstance(clause, dict):
            continue
        clause_id = str(clause.get("clause_id") or "")
        clause_text = str(clause.get("clause_text") or "")
        if "本地注册" in clause_text or "本地办公" in clause_text:
            findings.append(
                {
                    "clause_id": clause_id,
                    "rule_code": "R1",
                    "risk_title": "地域限制条款",
                    "risk_level": "高",
                    "risk_category": "公平竞争",
                    "evidence_text": "供应商须本地注册并在本地办公。",
                    "review_reasoning": "条款直接要求供应商具备本地注册或办公条件，可能形成地域限制。",
                    "need_human_confirm": False,
                }
            )
        if "综合评价" in clause_text or "酌情打分" in clause_text:
            findings.append(
                {
                    "clause_id": clause_id,
                    "rule_code": "R9",
                    "risk_title": "评分项未量化",
                    "risk_level": "高",
                    "risk_category": "评审可解释性",
                    "evidence_text": "采用综合评价并可酌情打分。",
                    "review_reasoning": "评分表述存在主观裁量空间，缺少明确量化口径。",
                    "need_human_confirm": True,
                }
            )
        if "品牌" in clause_text or "型号" in clause_text or "专利" in clause_text:
            findings.append(
                {
                    "clause_id": clause_id,
                    "rule_code": "R5",
                    "risk_title": "品牌型号指向",
                    "risk_level": "高",
                    "risk_category": "公平竞争",
                    "evidence_text": clause_text,
                    "review_reasoning": "条款直接出现品牌、型号或专利类表述，需警惕定向限制。",
                    "need_human_confirm": True,
                }
            )
    return findings


def _extract_embedded_json(user_message: str) -> dict[str, object]:
    candidates = [index for index, char in enumerate(user_message) if char == "{"]
    end = user_message.rfind("}")
    if end == -1:
        return {}
    for start in reversed(candidates):
        try:
            parsed = json.loads(user_message[start : end + 1])
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    return {}


@contextmanager
def fake_llm_environment():
    previous_env = {
        key: os.environ.get(key)
        for key in (
            "OPENAI_BASE_URL",
            "OPENAI_API_KEY",
            "OPENAI_MODEL",
            "OPENAI_TIMEOUT_SECONDS",
            "OPENAI_REVIEW_BATCH_SIZE",
            "OPENAI_REVIEW_CLAUSE_MAX_CHARS",
            "OPENAI_MAX_COMPLETION_TOKENS",
            "OPENAI_REASONING_EFFORT",
        )
    }
    server = ThreadingHTTPServer(("127.0.0.1", 0), _FakeLlmHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    host, port = server.server_address
    os.environ["OPENAI_BASE_URL"] = f"http://{host}:{port}/v1"
    os.environ["OPENAI_API_KEY"] = "test-key"
    os.environ["OPENAI_MODEL"] = "fake-gpt"
    os.environ["OPENAI_TIMEOUT_SECONDS"] = "10"
    os.environ["OPENAI_REVIEW_BATCH_SIZE"] = "4"
    os.environ["OPENAI_REVIEW_CLAUSE_MAX_CHARS"] = "800"
    os.environ["OPENAI_MAX_COMPLETION_TOKENS"] = "256"
    os.environ["OPENAI_REASONING_EFFORT"] = "low"
    try:
        yield
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)
        for key, value in previous_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
