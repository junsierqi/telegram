# Document Maintenance Rules

## Rule

Architecture docs are part of the implementation. They are not optional follow-up material.

## Required updates

Any code change that affects one of the following must also update the matching document in the same change set:

- module boundaries
- folder structure
- transport protocols
- message lifecycle
- authentication model
- storage model
- remote-control session flow
- UI navigation flow
- page or dialog state transitions
- executable entry points
- repository structure

## Source of truth

- `docs/architecture/*.md` defines module intent and boundaries
- `docs/flows/*.md` defines user-visible and system-visible workflows
- `docs/diagrams/*.mmd` defines visual architecture and state/sequence diagrams

If implementation and docs disagree, the change is incomplete.

## Update checklist

Before closing a task:

1. Check whether the code changed any module responsibilities.
2. Check whether any UI states or flows changed.
3. Update Mermaid diagrams if interactions changed.
4. Update `README.md` if project entry points changed.
5. Mention doc updates in the change summary.
