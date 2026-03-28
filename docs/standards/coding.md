# Coding Standards

## General

- Prefer readable, boring defaults over cleverness.
- Keep modules small and ownership boundaries explicit.
- Add comments only when they preserve intent that is hard to infer from code.
- Avoid hidden side effects in scripts and automation.

## Agent-Focused Guidance

- Name files and commands so they are easy to discover.
- Keep setup and validation commands short and predictable.
- Reuse existing entrypoints before adding new ones.
- If a new invariant matters, encode it in automation instead of relying on
  memory.

## Documentation

- Update docs in the same change when behavior or workflow changes.
- Prefer focused documents over one large instruction file.
