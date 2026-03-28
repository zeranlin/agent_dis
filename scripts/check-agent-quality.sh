#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

check_file_contains() {
  local file="$1"
  local pattern="$2"

  if ! grep -q "$pattern" "${ROOT_DIR}/${file}"; then
    echo "Missing required section '${pattern}' in ${file}" >&2
    exit 1
  fi
}

required_files=(
  "docs/standards/agent-quality-rules.md"
  "docs/templates/task-template.md"
  "docs/logs/experiments.md"
  "docs/logs/decisions.md"
)

for file in "${required_files[@]}"; do
  if [[ ! -f "${ROOT_DIR}/${file}" ]]; then
    echo "Missing required file: ${file}" >&2
    exit 1
  fi
done

check_file_contains "docs/templates/task-template.md" "## 摘要"
check_file_contains "docs/templates/task-template.md" "## 验证"
check_file_contains "docs/templates/task-template.md" "## 给下一个智能体的说明"
check_file_contains "docs/logs/experiments.md" "## 记录模板"
check_file_contains "docs/logs/experiments.md" "假设："
check_file_contains "docs/logs/experiments.md" "结果："
check_file_contains "docs/logs/decisions.md" "## 记录模板"
check_file_contains "docs/logs/decisions.md" "决策："
check_file_contains "docs/logs/decisions.md" "影响："
check_file_contains "docs/standards/agent-quality-rules.md" "## 评分维度"
check_file_contains "docs/standards/agent-quality-rules.md" "## 最小契约"
check_file_contains "docs/standards/agent-quality-rules.md" "## 审阅问题"

md_files=(
  "README.md"
  "AGENTS.md"
  ".github/pull_request_template.md"
  "docs/architecture.md"
  "docs/logs/experiments.md"
  "docs/logs/decisions.md"
  "docs/runbooks/change-checklist.md"
  "docs/standards/agent-quality-rules.md"
  "docs/standards/coding.md"
  "docs/standards/repository-contract.md"
  "docs/templates/task-template.md"
)

for file in "${md_files[@]}"; do
  if ! grep -q '[一-龥]' "${ROOT_DIR}/${file}"; then
    echo "Markdown file must contain Chinese content: ${file}" >&2
    exit 1
  fi
done

echo "Agent quality checks passed."
