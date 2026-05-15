# Implementation

Gate Status: READY

Rule: Do not edit business code until the user confirms `/idea execute` and `implementation ready` succeeds. Execute every TASK below autonomously after confirmation; stop only for scope ambiguity, destructive action, missing dependency, or a verified blocker.

## Execution Checklist

## TASK-1: Build the missing-tool and mouse-response audit matrix

Status: completed

Files:
- `client/src/app_desktop/main.cpp`
- `client/src/app_desktop/bubble_list_view.cpp`
- `client/src/app_desktop/bubble_list_view.h`
- `scripts/validate_desktop_button_responses.py`
- `scripts/validate_desktop_telegram_reference_ui.py`
- `scripts/validate_desktop_gui_smoke.py`
- `D:\code\tdesktop\Telegram\SourceFiles\ui\abstract_button.*`
- `D:\code\tdesktop\Telegram\SourceFiles\editor\color_picker.*`
- `D:\code\tdesktop\Telegram\SourceFiles\history\history_inner_widget.*`

Execution Details:
- Enumerate visible/current desktop tools and controls: header buttons, composer controls, message row action affordances, sidebar/drawer rows, right-panel rows, settings/modal rows, attachment controls, call/remote controls, and advanced tool rows.
- Mark each as implemented, status-only, inert, missing hover/press feedback, missing cursor behavior, missing release cleanup, or missing validation.
- Extract tdesktop reference behavior for reusable mouse semantics: press, release, leave, hover animation, cursor, ripple/pressed feedback, click handler activation, and click-vs-drag threshold patterns.
- Write the audit summary into `07-execution-log.md` before implementing.

Done Criteria:
- A concrete matrix exists listing surfaces, current behavior, target behavior, and planned fix category.
- Any item that requires new backend/protocol scope is explicitly identified before implementation.
- The matrix maps each follow-up implementation task to at least one REQ-ID.

Planned Verification:
- Manual source audit using `rg` over `client/src/app_desktop`, `scripts/validate_desktop_*.py`, and selected `D:\code\tdesktop\Telegram\SourceFiles` paths.
- `07-execution-log.md` contains the audit matrix and reference notes.

## TASK-2: Add shared desktop mouse-response primitives if repeated gaps exist

Status: completed

Files:
- `client/src/app_desktop/main.cpp`
- Optional new helper under `client/src/app_desktop/` only if repetition justifies it
- `CMakeLists.txt` only if a new helper source is added

Execution Details:
- Factor or centralize repeated hover/press/release/cursor handling for tool-like controls where the audit finds repeated ad hoc patterns.
- Match tdesktop semantics at behavior level: pressed state starts on left press, activation happens on release inside target, state clears on leave/release, cursor follows actionable region, and feedback is immediate.
- Avoid changing controls that already have specialized behavior unless they are listed in the audit matrix.

Done Criteria:
- Shared behavior reduces duplicated interaction code or standardizes existing ad hoc controls.
- Existing specialized components such as `BubbleListView` keep their message-specific behavior while gaining any missing cleanup/timing fixes identified in TASK-1.
- No broad UI framework rewrite is introduced.

Planned Verification:
- Compile `app_desktop` with `cmake --build build-codex-verify --config Debug --target app_desktop`.
- Add or update a static validator if a new helper/pattern is introduced.

## TASK-3: Complete visible tool behavior across desktop surfaces

Status: completed

Files:
- `client/src/app_desktop/main.cpp`
- `client/src/app_desktop/bubble_list_view.cpp`
- `client/src/app_desktop/bubble_list_view.h`
- Existing validators under `scripts/validate_desktop_*.py`

Execution Details:
- Implement missing responses from the TASK-1 audit for header/composer/message/right-panel/sidebar/drawer/settings/modal/attachment/call/remote/advanced controls.
- Prefer routing to existing UI pages, menus, RPC wrappers, local state, or explicit disabled/blocked flows; avoid placeholder-only status messages unless the target behavior is intentionally unavailable and documented.
- Ensure mouse feedback is consistent: hover visible where actionable, press state visible, release action only fires correctly, leave clears state, right-click/context actions remain scoped.

Done Criteria:
- Every audited visible tool is either implemented, explicitly blocked with reason, or deferred with a non-critical acceptance note.
- High-priority user-facing controls no longer stop at inert or status-only behavior when an existing route/RPC is available.
- Cursor and hover/press feedback match the shared pattern or a documented specialized pattern.

Planned Verification:
- Run targeted validators for button responses, Telegram reference UI, sidebar/drawer, right panel, popup/menu, composer interactions, and GUI smoke static checks.
- Run `app_desktop_store_test.exe` after compile.

## TASK-4: Add durable validation for mouse timing and tool response coverage

Status: completed

Files:
- `scripts/validate_desktop_button_responses.py`
- `scripts/validate_desktop_telegram_reference_ui.py`
- `scripts/validate_desktop_popup_states.py`
- `scripts/validate_desktop_composer_interactions.py`
- `scripts/validate_bubble_list_view.py`
- Potentially a new focused validator, if existing scripts cannot express the audit matrix cleanly

Execution Details:
- Extend validators to assert the new mouse-response primitives or explicit event handling tokens.
- Add coverage for each newly implemented tool response so regressions are caught without relying only on screenshots.
- Keep validators static where possible; use GUI smoke only for flows that already have reliable runtime hooks.

Done Criteria:
- Each implemented TASK-3 category has at least one validator or test evidence path.
- Validators check meaningful behavior tokens, not just object names.
- Existing validators remain passing or are updated with intentional behavior changes.

Planned Verification:
- Run all updated validators.
- Run `python scripts/_sweep_validators.py` if runtime prerequisites are available; otherwise run the targeted subset and record skipped prerequisites.

## TASK-5: Build, smoke, and acceptance pass

Status: completed

Files:
- `05-verification.md`
- `06-acceptance.md`
- `07-execution-log.md`
- `08-final-report.md`
- No business files unless verification finds in-scope defects from TASK-2 through TASK-4

Execution Details:
- Build with `build-codex-verify`, matching prior project practice.
- Run `app_desktop_store_test.exe`.
- Run targeted desktop validators.
- Run `scripts/validate_desktop_gui_smoke.py` if the built binary and GUI environment are available.
- Record each TASK as PASS, PARTIAL, FAIL, or DEFERRED with evidence.

Done Criteria:
- `app_desktop` compiles in `build-codex-verify`.
- Store tests pass.
- Targeted validators pass.
- Any unavailable GUI/runtime evidence is explicitly recorded with reason and does not hide a critical gap.
- Final bundle verifies and is ready for finalize.

Planned Verification:
- `cmake --build build-codex-verify --config Debug --target app_desktop`
- `cmake --build build-codex-verify --config Debug --target app_desktop_store_test`
- `.\build-codex-verify\client\src\Debug\app_desktop_store_test.exe`
- Targeted `python scripts/validate_desktop_*.py` commands from TASK-4
- `python C:\Users\junsierqi\.codex\skills\idea-to-code\scripts\manage_delivery_bundle.py verify --root . --slug 20260515-0425-desktop-ui-tool-mouse-response-parity`
