# Execution Log

## Timeline

### TASK-1 Audit Matrix

Reference notes:
- `D:\code\tdesktop\Telegram\SourceFiles\editor\color_picker.cpp` uses explicit hover/pressed button state and click callbacks for tool buttons.
- `D:\code\tdesktop\Telegram\SourceFiles\history\history_inner_widget.cpp` clears active/pressed link state on leave/release and only activates the intended handler.
- The current app already has specialized message-list hover/pressed behavior in `BubbleListView`; that path is not duplicated.

| Surface | Current behavior | Target behavior | Fix category | REQ |
|---|---|---|---|---|
| Header/composer `QToolButton`/`QPushButton` controls | Native Qt hover/press plus concrete signal routes | Keep native behavior; do not rewrite specialized controls | No code change | REQ-1, REQ-3 |
| Message bubble action affordance | `BubbleListView` tracks hovered/pressed rows and clears on leave | Keep specialized message behavior | No code change | REQ-2 |
| Drawer Wallet row | Release route exists on row/children, but activation did not require a matching left press and had no shared pressed feedback | Left press starts state, leave/release clears state, release inside activates Wallet | Shared mouse-response primitive | REQ-2, REQ-3 |
| Drawer Emoji Status row | Release route exists, same missing press-inside/cleanup semantics | Same press-inside and cleanup semantics | Shared mouse-response primitive | REQ-2, REQ-3 |
| Settings General rows | Overlay button clicks route pages/toggles, but parent row feedback is not guaranteed because overlay owns mouse events | Overlay participates in shared hover/press feedback while preserving button click routing | Shared mouse-response primitive | REQ-2, REQ-3 |
| Settings theme/accent tools | Overlay buttons persist settings, but no shared pressed feedback validation | Add event-filtered pressed feedback to the wrappers | Shared mouse-response primitive | REQ-2, REQ-3 |
| Right-panel/profile/modal concrete buttons | Existing signal routes and native press behavior | Keep current concrete routes and validator coverage | Validator only | REQ-3, REQ-4 |

Implementation decision:
- No backend/protocol scope is required.
- Add a narrow `main.cpp` helper instead of a new source file because the repeated gap is limited to property-driven drawer/settings rows.
- Extend the existing static button-response validator to require press, release-inside, leave cleanup, and dynamic feedback properties.
