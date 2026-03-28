from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


REQUIRED_RULE_FIELDS = {
    "rule_id",
    "rule_code",
    "rule_name",
    "rule_domain",
    "execution_level",
    "risk_level",
    "version",
}


@dataclass
class PromptAsset:
    prompt_id: str
    prompt_name: str
    version: str
    content_text: str
    status: str


class ReviewAssetLoader:
    def __init__(self, root_dir: Path):
        self.root_dir = root_dir
        self.rule_pack_path = self.root_dir / "assets" / "review" / "rule-packs" / "default-rule-pack.v1.json"
        self.prompt_path = self.root_dir / "assets" / "review" / "prompts" / "review-task-instruction.v1.md"

    def load_rule_pack(self) -> list[dict[str, object]]:
        payload = json.loads(self.rule_pack_path.read_text(encoding="utf-8"))
        rules = payload["rules"]
        for rule in rules:
            missing = REQUIRED_RULE_FIELDS - set(rule.keys())
            if missing:
                raise ValueError(f"规则缺少必要字段: {', '.join(sorted(missing))}")
        return rules

    def load_prompt_asset(self) -> PromptAsset:
        content = self.prompt_path.read_text(encoding="utf-8").strip()
        return PromptAsset(
            prompt_id="prompt_review_task_instruction_v1",
            prompt_name="固定审查任务指令",
            version="v1",
            content_text=content,
            status="active",
        )
