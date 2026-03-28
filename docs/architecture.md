# Architecture

## Purpose

This repository is intentionally structured for agent-assisted software
development. The main architectural requirement is clarity: both humans and
agents should be able to infer where code, documentation, and validation belong.

## Current Boundaries

The repository currently provides the collaboration harness itself:

- Repository entrypoints
- Documentation structure
- Validation hooks
- Review and change-management templates

Application-specific code should be added only after its owning area is made
explicit in this document.

## Structural Rules

- Root files should stay few and high signal.
- Long-lived knowledge belongs under `docs/`.
- Automation belongs under `scripts/` or `.github/workflows/`.
- Every new top-level directory should have an explicit reason.

## Change Policy

If you add a new subsystem, update this file with:

1. What the subsystem owns
2. What it depends on
3. How it is validated
