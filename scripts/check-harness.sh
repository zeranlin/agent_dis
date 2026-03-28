#!/usr/bin/env bash

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

required_files=(
  "README.md"
  "AGENTS.md"
  "docs/architecture.md"
  "docs/standards/repository-contract.md"
  "docs/standards/coding.md"
  "docs/standards/agent-quality-rules.md"
  "docs/runbooks/change-checklist.md"
  "docs/templates/task-template.md"
  "docs/tasks/current.md"
  "docs/tasks/backlog.md"
  "docs/tasks/done.md"
  "docs/tasks/template.md"
  "docs/logs/experiments.md"
  "docs/logs/decisions.md"
  "scripts/check-harness.sh"
  "scripts/check-agent-quality.sh"
  "Makefile"
  ".github/pull_request_template.md"
)

for file in "${required_files[@]}"; do
  if [[ ! -f "${ROOT_DIR}/${file}" ]]; then
    echo "Missing required file: ${file}" >&2
    exit 1
  fi
done

grep -q "make check" "${ROOT_DIR}/AGENTS.md" || {
  echo "AGENTS.md must direct agents to run make check" >&2
  exit 1
}

grep -q "docs/tasks/current.md" "${ROOT_DIR}/AGENTS.md" || {
  echo "AGENTS.md must direct agents to read docs/tasks/current.md" >&2
  exit 1
}

grep -q "scripts/check-harness.sh" "${ROOT_DIR}/Makefile" || {
  echo "Makefile must call scripts/check-harness.sh" >&2
  exit 1
}

grep -q "scripts/check-agent-quality.sh" "${ROOT_DIR}/Makefile" || {
  echo "Makefile must call scripts/check-agent-quality.sh" >&2
  exit 1
}

echo "Harness checks passed."
