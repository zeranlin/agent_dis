# agent_dis

An agent-first repository scaffold inspired by OpenAI's "harness engineering"
approach.

This repository is set up so humans and coding agents can share the same source
of truth:

- `AGENTS.md` is the top-level navigation file for agents.
- `docs/` stores durable knowledge that should stay in the repository.
- `scripts/check-harness.sh` validates the minimum repository contract.
- `Makefile` provides one entrypoint for local checks.

## Quick Start

```bash
make check
```

## Repository Shape

- `AGENTS.md`: agent navigation and working contract
- `docs/architecture.md`: system boundaries and intended structure
- `docs/standards/`: coding and repository invariants
- `docs/runbooks/`: repeatable workflows and change checklists
- `.github/`: pull request template

## Working Principle

The goal is not to stuff every instruction into one file. Instead:

1. Keep the repository as the source of truth.
2. Keep `AGENTS.md` short and navigational.
3. Encode important rules into scripts and CI where possible.
4. Prefer small, reviewable changes with explicit validation steps.
