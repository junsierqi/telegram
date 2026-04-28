# Requirements

- Target outcome: Deliver a runnable Telegram-like chat platform that keeps chat, desktop UX, persistence, deployment, TLS, and later remote-control work moving in verified, reversible slices.
- Primary user: A developer/operator validating the Windows desktop client and Python control-plane server in local, Docker, SQLite, and PostgreSQL-backed environments.
- Main flow: keep the existing chat desktop and server runnable, choose the next highest-priority gap from the task library, implement the smallest useful slice, verify locally, record evidence, and defer external side effects into pending actions until approved.
- Success criteria:
  - Every implemented slice has a REQ-ID, a checkpoint, and concrete verification evidence.
  - Documentation and runnable commands stay aligned with actual code.
  - SQLite/default and PostgreSQL/deployment paths do not regress silently.
  - External side effects such as Docker startup, pushes, deployments, signing, or network pulls are recorded as pending actions unless explicitly confirmed.
- Non-goals:
  - Do not ship mobile clients, production certificate automation, signed installers, or real remote-desktop media runtime in the current slice.
  - Do not run live Docker/deployment actions without confirmation.
- Constraints:
  - Preserve the current C++20 client and Python stdlib server architecture.
  - Prefer local static/unit validators before live integration.
  - Keep generated certificates and runtime state out of git.
- Unknowns:
  - Whether direct C++ TLS should use Qt TLS, OpenSSL, SChannel, or a small transport abstraction in the next parity slice.
  - Whether production PostgreSQL TLS should be mandatory through proxy termination or native server TLS.
