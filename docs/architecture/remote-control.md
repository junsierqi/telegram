# Remote-Control Extension

## Goal

Add remote-control capability on top of the chat product without breaking the existing chat architecture.

This feature is treated as a separate subsystem that reuses the account and device foundation but keeps its own transport and media path.

This is a first-party implementation target. The product may feel similar to `AnyDesk`, but the architecture assumes in-house host, viewer, negotiation and relay components rather than launching or embedding a third-party remote desktop tool. `RustDesk` is a reasonable reference point for system decomposition, especially around host, rendezvous, relay and session setup.

## Product positioning

- chat product first, remote desktop second
- remote desktop is built into the client and service stack
- no dependency on external remote-control executables for core functionality
- account, trust and device identity come from the chat platform

## Reused foundations from chat

- account identity
- friendship or trust relationships
- device registry
- online presence
- notification delivery
- session invite patterns
- audit and permission model

## New remote-control capabilities

### On the client

- remote request dialog
- approval dialog
- screen capture host module
- input capture and injection modules
- decoder and renderer surface
- remote session HUD and state machine
- host runtime and viewer runtime that can evolve toward a RustDesk-like split

### On the server

- remote session invite API
- device capability registry
- rendezvous or session-discovery service
- NAT traversal negotiation
- relay assignment
- session audit events
- policy checks

### Optional later service split

- dedicated relay service
- TURN-like fallback
- metrics and QoS service

## Channel separation

The system must use at least two logical channels:

- control channel
  carries auth, invites, approvals, policy, metadata and state updates
- media channel
  carries screen frames, input events, optional audio and clipboard sync

This separation is mandatory. Regular chat message transport is not suitable for low-latency remote control.

In practice this means:

- chat messages and presence events stay on the existing control-plane path
- remote desktop session setup uses dedicated coordination messages and short-lived credentials
- screen, input and optional audio flow over direct or relayed real-time transports owned by this project

## Remote session flow

1. User A opens a chat or device list and requests control of Device B.
2. Server validates identity, trust relationship and device status.
3. Device B receives an approval request.
4. If approved, the server negotiates direct or relayed connectivity.
5. Media and input channels are established.
6. The session remains visible in both clients and emits audit events.
7. On end or disconnect, state and audit records are finalized.

## Security direction

- explicit user approval for attended sessions
- optional unattended access later
- device trust records
- short-lived session tokens
- end-to-end encryption for control and media where feasible
- visible session indicators
- full audit trail

## Remote-control MVP boundary

- Windows host first
- desktop viewer on Windows first
- screen stream
- mouse and keyboard
- session request and approval
- relay fallback
- project-owned host, viewer, rendezvous and relay components

Deferred:

- macOS host
- Linux host
- audio
- multi-monitor
- file sync inside remote session

## Reference direction

Useful reference themes from `RustDesk`-like systems:

- separate rendezvous and relay responsibilities
- prefer direct connectivity, with relay fallback
- keep host and viewer state machines explicit
- isolate binary media transport from product control-plane logic
- treat unattended access as a stricter later-phase security model, not an MVP default

## Diagrams

- [Remote control architecture](../diagrams/remote-control-architecture.mmd)
- [Remote session sequence](../diagrams/remote-session-sequence.mmd)
