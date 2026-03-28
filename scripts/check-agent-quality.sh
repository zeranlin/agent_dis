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
  "docs/standards/agent-quality-rubric.md"
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

check_file_contains "docs/templates/task-template.md" "## Summary"
check_file_contains "docs/templates/task-template.md" "## Validation"
check_file_contains "docs/templates/task-template.md" "## Notes For The Next Agent"
check_file_contains "docs/logs/experiments.md" "## Entry Template"
check_file_contains "docs/logs/experiments.md" "Hypothesis:"
check_file_contains "docs/logs/experiments.md" "Result:"
check_file_contains "docs/logs/decisions.md" "## Entry Template"
check_file_contains "docs/logs/decisions.md" "Decision:"
check_file_contains "docs/logs/decisions.md" "Consequences:"
check_file_contains "docs/standards/agent-quality-rubric.md" "## Scoring Model"
check_file_contains "docs/standards/agent-quality-rubric.md" "## Minimum Contract"
check_file_contains "docs/standards/agent-quality-rubric.md" "## Review Questions"

echo "Agent quality checks passed."
