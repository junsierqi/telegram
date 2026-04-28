# PRD

## Goal

- Continue the Telegram-like platform through autonomous, verified improvement slices, with a persistent Atlas task library and delivery plan in the existing idea-to-code bundle.

## Users

- Developers validating local desktop/server behavior.
- Operators validating Docker, TLS, SQLite, and PostgreSQL deployment paths.

## Main Flows

- Scan current state and backlog.
- Select the next priority that can be implemented without unapproved external side effects.
- Implement and verify locally.
- Record milestone status, pending actions, risks, and next priority.

## Scope

- In scope: task library upkeep, docs alignment, static validators, local code changes, bundle checkpointing.
- Out of scope: unapproved Docker startup, deployment, git push, release signing, production certificate provisioning.

## Functional Requirements

- REQ-ATLAS-TASK-LIBRARY: Maintain a human-readable task library with priorities, state, evidence, and pending external actions.
- REQ-TLS-PG-PROXY: Provide TLS termination coverage for the PostgreSQL-backed Docker server profile, matching the existing SQLite-backed TLS proxy pattern.

## Technical Shape

- Use `.idea-to-code/telegram-platform` as the durable task and delivery bundle.
- Keep Docker TLS proxy configuration under `deploy/docker` and `deploy/tls`.
- Extend existing `scripts/validate_tls_deployment_config.py` for static safety checks; live Docker smoke remains a pending action until approved.

## Acceptance

- Local static validation passes.
- Bundle verification passes or any uncovered requirement is explicitly checkpointed/blocked.
- Pending external actions are recorded and not executed without confirmation.
