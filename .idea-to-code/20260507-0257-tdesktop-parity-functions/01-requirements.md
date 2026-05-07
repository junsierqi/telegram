# Requirements

- Target outcome: continue Telegram Desktop 1:1 function/UI parity for the current desktop shell.
- Primary user: desktop client user operating profile, contacts, right info panel, drawer and settings flows.
- Main flow: use tdesktop-inspired UI surfaces, route visible controls to real local/server behavior, and keep validators/docs synchronized.
- Success criteria: Profile modal, Contacts dialog, right-panel Report/Leave/shared-media, and the corresponding backend contracts have implementation plus targeted validation evidence.
- Non-goals: full Premium/Gift/Wallet/Stories backend product domains and full pixel-perfect screenshot parity across all reference images.
- Constraints: no commit unless explicitly requested; preserve existing validators and C++ buildability.
- Unknowns: local screenshot diff baselines may remain stricter than the functional/UI parity scope.
