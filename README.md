# agent_dis

An agent-first repository scaffold inspired by OpenAI's "harness engineering"
approach.

This repository is set up so humans and coding agents can share the same source
of truth while building `agent_dis` in an incremental, agent-first way:

- `AGENTS.md` is the top-level navigation file for agents.
- `docs/` stores durable knowledge that should stay in the repository.
- `docs/templates/` defines task intake structure.
- `docs/logs/` captures experiments and decisions over time.
- `scripts/check-harness.sh` validates the minimum repository contract.
- `scripts/check-agent-quality.sh` validates the agent-quality rubric contract.
- `Makefile` provides one entrypoint for local checks.

## Quick Start

```bash
make check
```

## Repository Shape

- `AGENTS.md`: agent navigation and working contract
- `docs/architecture.md`: system boundaries and intended structure
- `docs/templates/`: templates for new work items
- `docs/logs/`: experiment and decision history
- `docs/standards/`: coding and repository invariants
- `docs/runbooks/`: repeatable workflows and change checklists
- `.github/`: pull request template

## Working Principle

The goal is not to stuff every instruction into one file. Instead:

1. Keep the repository as the source of truth.
2. Keep `AGENTS.md` short and navigational.
3. Encode important rules into scripts and CI where possible.
4. Prefer small, reviewable changes with explicit validation steps.

## Current Focus

The current phase of `agent_dis` is to establish a durable operating harness for
agent-driven delivery:

- clarify the product boundary before implementation expands
- standardize task intake and validation
- keep experiment outcomes and architecture decisions inside the repository
- make agent output quality visible and machine-checkable
