# Project Task Library

Status date: 2026-04-28

## Operating Rules

- Chat updates and reports about delivery work use the `[idea-to-code]` prefix from the idea-to-code skill itself. No other speaker prefix is required.
- This file is the project-local task backlog: prioritized tasks, REQ-ID mapping, and pending external actions. The idea-to-code delivery bundle remains under `.idea-to-code/telegram-platform/`.
- External side effects stay in Pending Actions until confirmed: Docker start/stop, deployment, network pulls, git push, package signing, production certificate creation, and destructive cleanup.
- Each implementation task must map to a REQ-ID and checkpoint in this bundle.
- Prefer static/local validators before live integration.

## Current Delivery Plan

1. M66 PostgreSQL TLS proxy coverage: ✅ static validation in place; live smoke pending PA-001/PA-002.
2. M67 C++ TLS client transport parity: ✅ direct TLS login + sync verified end-to-end on build-verify.
3. M68 Schannel credential fix: ✅ explicit SCHANNEL_CRED resolves SEC_E_NO_CREDENTIALS; smoke green.
4. M69 Deployment hardening acceptance sweep: rerun TLS, packaging, SQLite, PostgreSQL, and desktop smoke validators; live Docker checks remain pending until approved.

## Task Backlog

| ID | Priority | State | Requirement | Task | Verification | External side effects |
|---|---:|---|---|---|---|---|
| ATLAS-M66 | P0 | in_progress | REQ-TLS-PG-PROXY | Add PostgreSQL-backed Docker TLS proxy profile and static validation. | `python scripts\validate_tls_deployment_config.py`; `docker compose ... config` only if approved/available. | Live `docker compose up` and TLS proxy smoke on 8444 pending approval. |
| ATLAS-M67 | P0 | done | REQ-TLS-CPP-CLIENT | Add direct TLS client transport parity for C++ desktop/CLI without changing UI code. | M68 fix verified: validate_cpp_tls_client.py 2/2, e2e 3/3, store 20/20. | None — runtime acceptance achieved via explicit SCHANNEL_CRED. |
| ATLAS-M68 | P0 | done | REQ-TLS-CPP-CLIENT,REQ-TLS-CONTROL-PLANE,REQ-VALIDATION | Resolve Schannel `SEC_E_NO_CREDENTIALS` by passing explicit SCHANNEL_CRED to AcquireCredentialsHandleW. | Build clean, TLS smoke + chat E2E + desktop store + TLS deployment static all pass. | None. |
| ATLAS-M69 | P1 | planned | REQ-VALIDATION | Deployment hardening acceptance sweep (full run of validate_* scripts) after TLS direct-client lands. | TLS validators, package validator, desktop smoke, PostgreSQL validators. | Docker container lifecycle and network pulls pending approval. |
| ATLAS-M70 | P1 | planned | REQ-WINDOWS-PACKAGE-STAGING | Move Windows package from staged zip/checksums toward installer/signing plan. | Package validator and checksum verification. | Signing certificate and installer publishing pending approval. |
| ATLAS-M71 | P2 | planned | REQ-REMOTE-LIFECYCLE | Resume remote-control runtime path after chat/deployment hardening. | Remote session validators and media-plane tests. | None expected until live multi-client smoke. |

## Pending Actions

| ID | Created | Action | Reason | Confirmation needed |
|---|---|---|---|---|
| PA-001 | 2026-04-27 | `docker compose -f deploy/docker/docker-compose.yml --profile postgres --profile tls up -d postgres telegram-server-postgres telegram-tls-proxy-postgres` | Start live PostgreSQL-backed TLS proxy stack for integration smoke. | Yes |
| PA-002 | 2026-04-27 | `python scripts\validate_tls_proxy_smoke.py --port 8444 --device dev_tls_proxy_pg_smoke` | Verify real login through PostgreSQL TLS proxy after PA-001. | Yes |
| PA-003 | 2026-04-27 | `docker compose -f deploy/docker/docker-compose.yml --profile postgres --profile tls config` | Static compose expansion may depend on local Docker/WSL availability. | Yes if Docker/WSL access requires escalation |

## Notes

- ATLAS-M67/M68 are PASS: native TLS handshake now succeeds via explicit SCHANNEL_CRED, and the full local sweep (`validate_cpp_tls_client`, `validate_cpp_chat_e2e`, `app_desktop_store_test`, `validate_tls_deployment_config`) is green on `build-verify`.
- Highest-priority no-external-side-effect slice is now ATLAS-M69 (full validator sweep).
- PA-001/PA-002/PA-003 still require user approval before live PostgreSQL Docker TLS smoke can run.
