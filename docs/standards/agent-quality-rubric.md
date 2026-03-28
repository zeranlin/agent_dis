# Agent Quality Rubric

This rubric defines the minimum quality bar for agent-authored output in this
repository.

## Scoring Model

Each change should be reviewable against five dimensions:

1. Intent clarity: the task and expected outcome are explicit
2. Traceability: decisions and experiments are captured in the repository
3. Validation: checks or manual verification are described
4. Repository fit: changes follow the documented structure and entrypoints
5. Maintainability: another human or agent can continue the work

The goal of the script is not to grade semantics perfectly. It enforces that the
repository contains the artifacts needed for this rubric to be applied
consistently.

## Minimum Contract

The following artifacts must exist and contain the documented sections:

- `docs/templates/task-template.md`
- `docs/logs/experiments.md`
- `docs/logs/decisions.md`

## Review Questions

Use these questions during review:

1. Can someone understand the task without rereading the chat?
2. Is the expected validation explicit?
3. Were meaningful learnings recorded as experiments or decisions?
4. Did the change extend existing repository pathways instead of inventing new
   hidden ones?
5. Could another agent resume work safely from the repository alone?
