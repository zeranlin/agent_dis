# Architecture

## Purpose

`agent_dis` is currently a delivery harness for building an agent-first project
without letting the repository dissolve into undocumented prompts, one-off
scripts, or untraceable changes.

The immediate goal is not maximum feature volume. The goal is to make future
feature work legible:

- humans can understand what the project is trying to do
- agents can discover where to place new work
- reviewers can validate output against explicit standards

## Product Assumption

Until application code exists, the repository's working assumption is:

`agent_dis` will be developed primarily through human-guided agent execution,
with the repository acting as the system of record for scope, quality gates, and
architectural decisions.

If the product mission changes, update this section first before expanding the
codebase.

## Current System Layers

The repository currently has four layers.

### 1. Navigation Layer

Entry files that tell humans and agents where to start:

- `README.md`
- `AGENTS.md`

### 2. Knowledge Layer

Durable documents that preserve intent and constraints:

- `docs/architecture.md`
- `docs/standards/`
- `docs/runbooks/`
- `docs/templates/`
- `docs/logs/`

### 3. Control Layer

Executable checks that keep the repository contract enforceable:

- `Makefile`
- `scripts/check-harness.sh`
- `scripts/check-agent-quality.sh`

### 4. Delivery Layer

The future home of product code, services, prompts, evaluations, and
integration-specific implementation. This layer should not grow until ownership
and validation are documented here.

## Planned Expansion Path

When product code is added, expand the repository in this order:

1. Define the subsystem and owner in this document.
2. Define its validation method.
3. Add or update the task template fields needed for that subsystem.
4. Add implementation files.

This ordering is intentional: design the harness before increasing throughput.

## Structural Rules

- Root files should stay few and high signal.
- Long-lived knowledge belongs under `docs/`.
- Repeatable checks belong in `scripts/`.
- Templates should describe new work before work begins.
- Logs should preserve what was learned after work finishes.
- Every new top-level directory should have an explicit reason in this file.

## Required Traceability

Every material change should leave an artifact in at least one of these places:

- `docs/templates/task-template.md` for the shape of a new task
- `docs/logs/experiments.md` for tested hypotheses and outcomes
- `docs/logs/decisions.md` for durable choices with consequences

## Change Policy

If you add a new subsystem, update this file with:

1. What the subsystem owns
2. What it depends on
3. How it is validated
4. Which log or template should capture its decisions and experiments
