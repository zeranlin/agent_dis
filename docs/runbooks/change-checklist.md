# Change Checklist

Use this checklist for human and agent-authored changes.

## Before Coding

1. Read `AGENTS.md` and the linked documents.
2. Confirm where the change belongs.
3. Start from `docs/templates/task-template.md` for any new work item.
4. Identify how the change will be validated.

## While Coding

1. Keep the change small enough to review quickly.
2. Update documentation if behavior, workflow, or structure changes.
3. Prefer extending existing scripts and checks instead of creating parallel
   paths.
4. Capture experiments and decisions as you learn, not only at the end.

## Before Review

1. Run `make check`.
2. Capture any additional manual validation performed.
3. Confirm docs still match the repository state.
4. If the change affected direction, architecture, or confidence, update the
   relevant log in `docs/logs/`.
