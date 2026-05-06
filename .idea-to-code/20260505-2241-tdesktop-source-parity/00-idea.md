# Idea

- Title: Telegram Desktop source parity UI
- Slug: 20260505-2241-tdesktop-source-parity
- Created At (UTC): 2026-05-06T05:41:05+00:00

## User Idea

Use local Telegram Desktop source at D:\code\tdesktop as implementation reference for 1:1 desktop UI parity.

## Desired Outcome

- Treat the local Telegram Desktop source tree as the primary UI reference, not only the screenshot set.
- Map tdesktop `.style` dimensions, spacing, and panel rules into this project's Qt desktop implementation in small verified passes.
- Keep existing desktop smoke/reference validators passing after every pass.
- Do not push; only commit when the user explicitly asks.
