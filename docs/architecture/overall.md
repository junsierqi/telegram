# Overall Architecture

> **Looking for what actually exists in the repo today?** Read
> [`current-state.md`](current-state.md) — directory tree + module-level
> annotations synced to the latest milestone. This file below captures
> product direction and long-term phase plan; some "current scaffold"
> descriptions predate the E-series and A+B arcs.

## Goal

Build a multi-platform chat product with:

- `C++20` client
- `Python` server
- chat-first delivery
- future remote-control capability on the same account, device and session foundation

The remote-control target is a self-implemented product capability, not an integration with third-party software such as `AnyDesk`. Product shape may resemble tools in that category, while technical direction can borrow from `RustDesk`-style host, relay and session architecture.

The project is not a clone of Telegram internals. It is a new product that borrows proven product directions:

- fast chat delivery
- multi-device account access
- direct and group messaging
- file transfer
- extensible real-time session capabilities

## System scope

The system is split into:

- client application
- control-plane server
- media and relay services added later for real-time sessions and remote control
- persistence and object storage

## High-level modules

### Client

- authentication UI and session management
- contacts and conversation list
- chat window and message composer
- file transfer UI
- notifications and presence UI
- device management UI
- session negotiation UI for calls and future remote control

### Server

- account and auth services
- websocket or TCP session gateway
- message routing
- conversation and membership management
- file metadata service
- presence and device registry
- notification and offline delivery
- audit and admin hooks

### Future remote-control extension

- remote session request and approval
- target device capability registry
- NAT traversal coordination
- relay fallback
- screen/audio/input control channels

This extension is intended to become a first-party remote desktop subsystem:

- chat remains the user-facing entry point and trust surface
- remote desktop transport, codecs, capture and input paths are implemented in project-owned modules and services
- external remote-control applications are out of scope for the core product architecture

## Architectural direction

The system uses a layered model:

1. Product layer
   UI flows, permissions, business actions, user-visible states
2. Application layer
   use cases, view models, orchestration, validation
3. Domain layer
   accounts, chats, messages, devices, sessions, permissions
4. Infrastructure layer
   transport, storage, cache, file/object store, push delivery

The remote-control feature will reuse:

- user identity
- contact trust
- device registration
- connection negotiation
- online presence

It will not reuse the regular chat message path for media transport. Chat remains control-plane. Media and input streams use dedicated real-time channels.

## Phase plan

### Phase 1: chat MVP

- register and log in
- manage profile
- add contacts
- one-to-one chat
- group chat
- offline message delivery
- file attachment metadata flow
- multi-device login

### Phase 2: real-time session foundation

- device capability registration
- session invite model
- heartbeat and reconnection model
- transport abstraction for real-time channels
- stronger security and session approval flows

### Phase 3: remote-control MVP

- request remote-control session from chat or device panel
- recipient approval
- screen stream
- mouse and keyboard control
- relay fallback
- session logging
- first-party host and viewer runtime on Windows

### Phase 4: advanced remote-control

- file handoff during control session
- multi-monitor
- audio redirection
- unattended access
- admin policies
- stronger direct-connect and relay strategy inspired by mature remote-desktop systems such as `RustDesk`

## Repository structure

```text
client/
  src/
    app/
    auth/
    chat/
    contacts/
    devices/
    remote_control/
    transport/
server/
  server/
    services/
shared/
  include/shared/protocol/
docs/
  architecture/
  flows/
  diagrams/
```

Current implementation status:

- `client/src/app`: application shell and startup entry
- `client/src/auth`: auth controller placeholder
- `client/src/chat`: chat controller placeholder
- `client/src/contacts`: contact controller placeholder
- `client/src/devices`: device controller placeholder
- `client/src/remote_control`: remote-session placeholder
- `client/src/transport`: control-plane gateway client placeholder
- `server/server/services`: auth, chat, presence and remote-session service placeholders
- `shared/include/shared/protocol`: shared control-plane message vocabulary

## Diagrams

- [System landscape](../diagrams/system-landscape.mmd)
- [Development roadmap](../diagrams/development-roadmap.mmd)
