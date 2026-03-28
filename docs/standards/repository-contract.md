# Repository Contract

This file defines repository-level invariants that agents and humans should
preserve.

## Required Files

The following files must exist:

- `README.md`
- `AGENTS.md`
- `docs/architecture.md`
- `docs/standards/coding.md`
- `docs/runbooks/change-checklist.md`
- `scripts/check-harness.sh`
- `Makefile`

## Repository Invariants

- `AGENTS.md` should remain a navigation file, not a dumping ground.
- Every durable workflow change should update `docs/`.
- `make check` must stay green.
- CI should call the same validation entrypoint used locally.

## Review Expectations

Changes should answer these questions:

1. What changed?
2. Why did it change?
3. How was it validated?
4. What docs were updated, or why were no doc changes needed?
