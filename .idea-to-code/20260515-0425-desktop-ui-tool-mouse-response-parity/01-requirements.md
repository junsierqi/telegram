# Requirements

- Target outcome: Complete missing desktop UI tool interactions and mouse-response behavior by comparing the current Qt Widgets desktop client with relevant Telegram Desktop patterns under `D:\code\tdesktop`.
- Primary user: A desktop client user expecting Telegram Desktop-like responsiveness from toolbar buttons, row actions, composer tools, panels, menus, and message/list interactions.
- Main flow: Identify missing or inert desktop tools, map each to intended behavior, implement tdesktop-like hover/press/release/cursor/timing feedback, then verify through static validators, build, store tests, and GUI smoke where available.
- Success criteria: Every identified desktop tool has an explicit response path; mouse hover/press/release state clears correctly; click vs drag behavior is not confused; visual feedback timing is consistent with tdesktop-inspired values; validation coverage prevents regressions.
- Non-goals: Do not port Telegram Desktop wholesale. Do not rewrite the desktop UI framework. Do not change backend protocol unless an existing UI action is blocked by a missing client RPC and the need is proven during implementation.
- Constraints: Business-code edits are blocked until `03-implementation.md` is confirmed and `/idea execute` is issued. Use `build-codex-verify` for compile checks, matching prior project practice. Keep old `.idea-to-code` bundles in place.
- Unknowns: The exact set of "missing tools" must be established by an implementation-time audit of `client/src/app_desktop/main.cpp`, `bubble_list_view.*`, existing validators, and tdesktop reference patterns.

## Requirement IDs

- REQ-1: Inventory all desktop UI tool surfaces that are visible or intended to be visible but lack concrete click, hover, press, release, cursor, menu, or route behavior.
- REQ-2: Implement tdesktop-inspired mouse response semantics for shared desktop controls: hover feedback, pressed state, release activation, leave cleanup, cursor changes, and click-vs-drag tolerance.
- REQ-3: Complete missing tool behavior for high-priority desktop surfaces: header tools, composer tools, message row affordances, right panel actions, drawer/sidebar rows, settings/modal tool rows, attachment/remote/call tools, and advanced tool rows.
- REQ-4: Add or extend validators so missing tool wiring and mouse-response regressions are mechanically detected.
- REQ-5: Verify the result with compile, targeted static validators, store tests, and GUI smoke/runtime checks where available.
