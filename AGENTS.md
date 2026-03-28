# AGENTS.md

This file is the entrypoint for coding agents working in this repository.

## Start Here

Before making changes, read these files in order:

1. `README.md`
2. `docs/architecture.md`
3. `docs/standards/repository-contract.md`
4. `docs/standards/agent-quality-rubric.md`
5. `docs/runbooks/change-checklist.md`

Then run:

```bash
make check
```

## Operating Rules

- Treat this repository as the system of record.
- Put durable decisions in `docs/`, not only in chats or PR comments.
- Keep changes small and easy to review.
- If you introduce a new workflow or invariant, document it and automate it.
- When documentation and code drift, fix the drift in the same change when
  possible.

## Where Knowledge Lives

- Architecture and boundaries: `docs/architecture.md`
- Repository invariants: `docs/standards/repository-contract.md`
- Coding standards: `docs/standards/coding.md`
- Agent quality rubric: `docs/standards/agent-quality-rubric.md`
- Task template: `docs/templates/task-template.md`
- Experiment log: `docs/logs/experiments.md`
- Decision log: `docs/logs/decisions.md`
- Change workflow: `docs/runbooks/change-checklist.md`

## Definition Of Done

A task is not done until:

1. The relevant docs are still accurate.
2. `make check` passes.
3. The validation steps are included in the change notes or PR.
4. New work that changes behavior, direction, or learning leaves an explicit
   trail in the appropriate template or log.
