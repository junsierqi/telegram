# Design

## Goal

Make the desktop UI feel complete and responsive by closing gaps between visible tools and implemented behavior, using `D:\code\tdesktop` as the interaction reference for mouse timing, hover/press feedback, click handling, and row/tool affordances.

## Reference Sources

- Current app:
  - `client/src/app_desktop/main.cpp`
  - `client/src/app_desktop/bubble_list_view.cpp`
  - `client/src/app_desktop/bubble_list_view.h`
  - existing `scripts/validate_desktop_*.py` validators
- Telegram Desktop reference:
  - `Telegram/SourceFiles/ui/abstract_button.*`
  - `Telegram/SourceFiles/ui/widgets/buttons.*`
  - `Telegram/SourceFiles/editor/color_picker.*`
  - `Telegram/SourceFiles/editor/photo_editor_controls.*`
  - `Telegram/SourceFiles/history/history_inner_widget.*`
  - `Telegram/SourceFiles/ui/chat/attach/*preview*`

## Technical Shape

- Add a shared desktop interaction helper only if the audit shows repeated hover/press/release/cursor code across multiple controls. Keep it local to `app_desktop` and avoid a broad UI framework rewrite.
- Prefer existing Qt primitives first: `QToolButton`, `QPushButton`, `eventFilter`, `QMouseEvent`, `QTimer`, `QCursor`, stylesheet/state properties, and focused validators.
- Use tdesktop-inspired behavior as semantics, not direct code copying:
  - active/pressed state is set on mouse press and cleared on release/leave
  - release activates only when still inside the intended target unless the control explicitly supports drag
  - cursor changes follow actionable region, not the whole container unless the whole row is clickable
  - hover/press feedback is immediate, while animated feedback uses short tdesktop-like durations where appropriate
  - click handlers are explicit and route to real UI/backend behavior, not status-only placeholders
- Preserve existing GUI smoke/reference behavior unless the implementation intentionally updates reference expectations and validators.

## Execution Strategy

1. Audit first, then implement. The audit is part of execution and must produce a concrete missing-tool matrix before code changes.
2. Implement shared mouse response behavior before per-tool fixes, so later tool work uses one pattern.
3. Close high-risk visible UI gaps before lower-priority debug/advanced controls.
4. Extend validators alongside implementation so each closed gap has durable coverage.
5. Verify with `build-codex-verify`, targeted validators, and GUI smoke where the existing environment supports it.

## Risk Controls

- If the audit finds a missing tool requiring new backend behavior outside existing RPC coverage, pause with `/idea stop` and update the plan before implementing that part.
- If tdesktop behavior conflicts with current project architecture, prefer local project patterns and document the deviation in `07-execution-log.md`.
- If GUI smoke artifacts are unavailable, record the gap in `05-verification.md` and use static validators plus compile/runtime smoke as the minimum evidence.
