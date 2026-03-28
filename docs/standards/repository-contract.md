# Repository Contract

This file defines repository-level invariants that agents and humans should
preserve.

## Required Files

The following files must exist:

- `README.md`
- `AGENTS.md`
- `docs/architecture.md`
- `docs/standards/coding.md`
- `docs/standards/agent-quality-rubric.md`
- `docs/runbooks/change-checklist.md`
- `docs/templates/task-template.md`
- `docs/logs/experiments.md`
- `docs/logs/decisions.md`
- `scripts/check-harness.sh`
- `scripts/check-agent-quality.sh`
- `Makefile`
- `.github/pull_request_template.md`

## Repository Invariants

- `AGENTS.md` should remain a navigation file, not a dumping ground.
- Every durable workflow change should update `docs/`.
- New work should have a traceable home in a template, experiment log, or
  decision log.
- `make check` must stay green.

## Review Expectations

Changes should answer these questions:

1. What changed?
2. Why did it change?
3. How was it validated?
4. What docs were updated, or why were no doc changes needed?
