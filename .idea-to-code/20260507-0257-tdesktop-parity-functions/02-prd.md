# PRD

## Goal

- Continue Telegram Desktop 1:1 function/UI parity for the current desktop shell.

## Users

- Desktop users operating profile, contacts, right info panel, drawer and settings flows.

## Main Flows

- Open Profile modal, inspect compact info/profile fields, and edit through Profile settings.
- Open Contacts, add/search/select a peer, edit alias, share contact text, or delete the contact.
- Use right info panel to report with a reason, leave with confirmation, and page shared media from the backend.

## Scope

- In scope: Profile modal tightening, Contacts peer-list actions, right-panel Report/Leave/shared-media contracts, typed client methods, validators and docs.
- Out of scope: full Premium/Gift/Wallet/Stories business domains and full pixel-perfect parity across every screenshot.

## Functional Requirements

- Visible desktop controls must have observable behavior or explicit backend/local routing.
- Backend contracts must validate report reason and leave confirmation.
- Shared media provider must page/filter media, files and links.

## Technical Shape

- Extend Python protocol/app/services/state, C++ ControlPlaneClient, Qt Widgets desktop flows, targeted validators, README and current architecture docs.

## Acceptance

- Targeted validators pass, C++ desktop build passes, app_desktop_store_test passes, docs are updated and no commit is made without explicit user instruction.
