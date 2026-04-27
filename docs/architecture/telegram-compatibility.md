# Telegram Compatibility Notes

## Purpose

Clarify how this project relates to Telegram technologies today and what it would mean to support Telegram connectivity later.

This repository currently builds:

- a first-party chat product
- a first-party remote desktop extension
- a project-owned control-plane protocol

It does not currently implement Telegram network compatibility.

## Current position

The project is `Telegram-like` in product direction, not Telegram-compatible in protocol terms.

That means:

- chat, multi-device state, updates and remote-session flows are inspired by mature messaging products
- client and server contracts in this repository are custom to this project
- the current `Python` server is not a Telegram server implementation
- the current `C++20` client is not a Telegram client implementation

## What to reference from Telegram

### TDLib

`TDLib` is the most useful Telegram reference for client architecture and state management.

Reference:

- https://core.telegram.org/tdlib
- https://core.telegram.org/tdlib/docs/
- https://core.telegram.org/tdlib/getting-started

Useful ideas to borrow:

- asynchronous request and response handling
- ordered update delivery
- strong local state synchronization
- clear client-side object model
- session management that survives unstable connections

### MTProto 2.0

`MTProto 2.0` is useful as a reference for session, connection and update-delivery thinking, not as a protocol to partially copy into the current stack.

Reference:

- https://core.telegram.org/mtproto
- https://core.telegram.org/mtproto/description
- https://core.telegram.org/api/updates

Useful ideas to borrow:

- session and connection are different concepts
- encrypted connections and authenticated sessions are separate steps
- updates should be pushed and ordered
- reconnect logic must preserve consistency

## What not to do right now

To keep this project moving, do not do the following in the current phase:

- do not try to make the custom `Python` server behave like Telegram servers
- do not try to gradually mix custom control-plane messages with Telegram protocol messages
- do not assume Telegram clients can talk to this server
- do not assume this client can talk to Telegram servers

Trying to make the current codebase simultaneously be:

- a self-owned chat and remote-desktop product
- a Telegram-compatible network client

would create conflicting architectural goals too early.

## Compatibility answer today

### Can this client talk to Telegram clients today?

No.

Reasons:

- protocol is different
- auth model is different
- transport and message schema are different
- Telegram clients expect Telegram servers and Telegram protocol behavior

### Can this server act as a Telegram server today?

No.

Reasons:

- no Telegram protocol compatibility
- no Telegram auth flow
- no Telegram update semantics
- no Telegram storage and API surface

## Recommended strategy

### Phase A: keep building the project-owned product

Continue current work on:

- client state model
- control-plane protocol
- chat synchronization
- multi-device handling
- remote-session negotiation
- later media, relay and remote-control runtime

### Phase B: isolate a future compatibility layer

If Telegram connectivity becomes important later, add a dedicated adapter layer instead of rewriting the whole project around compatibility.

Suggested direction:

- keep the current product protocol for your own server
- add a separate Telegram connector or adapter module
- keep Telegram-specific code out of the core domain model where possible
- treat Telegram as another backend integration, not the definition of the whole system

## Possible future integration shapes

### Option 1: TDLib-backed Telegram connector

Add a client-side integration that uses `TDLib` only for Telegram account access.

This would likely mean:

- one adapter for Telegram login and updates
- one mapping layer from Telegram objects into local app models
- separate boundaries for local chats versus Telegram-backed chats

This is the most realistic compatibility direction.

### Option 2: Telegram bridge service

Add a separate service that talks to Telegram APIs and translates updates into the local product model.

This keeps the desktop client simpler, but introduces a backend bridge with more operational complexity.

### Option 3: Full Telegram protocol compatibility

Rebuild major parts of the current stack around Telegram protocol assumptions.

This is the least attractive option for the current project because it would compete directly with the self-owned server and product protocol.

## Design rules for future compatibility

To keep the option open later, current code should preserve:

- stable domain models for users, devices, conversations, messages and sessions
- transport abstraction between app logic and network implementation
- a clean update/event pipeline
- a clear difference between product state and transport-specific state

These rules help both:

- the current project-owned server
- a future Telegram adapter

## Immediate implication for current development

Use Telegram as a design reference, not as an implementation target.

In practical terms:

- borrow client-state and update ideas from `TDLib`
- borrow session and update-delivery concepts from Telegram docs
- keep the current project protocol independent
- keep remote control entirely project-owned
