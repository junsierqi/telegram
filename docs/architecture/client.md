# Client Architecture

## Role

The client is a cross-platform desktop application written in `C++20`. It owns:

- UI rendering
- local session state
- network communication with the control-plane server
- local cache
- notifications
- file upload and download coordination
- future remote-control viewer and host capabilities

The remote-control direction is first-party. The desktop client is expected to grow its own host and viewer runtime instead of shelling out to an external tool.

## Main layers

### Presentation layer

- login and registration screens
- conversation list
- chat view
- settings
- device management
- remote-session dialogs

Recommended direction:

- `Qt 6` for multi-platform UI
- page and panel structure that can host both chat and remote-control surfaces later

### Application layer

- auth controller
- conversation controller
- message send pipeline
- attachment workflow
- presence and notification controller
- device session controller
- remote-session controller

This layer should coordinate UI and transport without knowing storage details.

### Domain layer

- `User`
- `Device`
- `Conversation`
- `Message`
- `Attachment`
- `SessionInvite`
- `RemoteControlSession`

### Infrastructure layer

- websocket or TCP client
- serializer
- local database
- file transfer worker
- logging
- platform adapters
- screen capture, encode/decode and input injection adapters for the future remote desktop stack

## Client modules

- `app_shell`
- `auth`
- `contacts`
- `chat`
- `attachments`
- `presence`
- `devices`
- `notifications`
- `remote_control`
- `platform`
- `transport`
- `storage`

## Current code scaffold

- `client/src/app/application.*`
- `client/src/app/app_shell.*`
- `client/src/auth/auth_controller.*`
- `client/src/chat/chat_controller.*`
- `client/src/contacts/contact_controller.*`
- `client/src/devices/device_controller.*`
- `client/src/remote_control/remote_session_controller.*`
- `client/src/transport/session_gateway_client.*`

These files currently define module entry points and preserve the boundaries from this document. UI technology such as `Qt 6` will be introduced after the chat domain and transport contracts are expanded beyond placeholders.

The later remote-control build-out should follow an AnyDesk-like product goal with a RustDesk-like engineering decomposition:

- chat UI starts the session
- host and viewer runtime live inside the client codebase
- session negotiation is separate from streaming and input transport

## Key client states

- signed_out
- connecting
- signed_in
- syncing
- ready
- reconnecting
- degraded

The remote-control subsystem will later add:

- remote_idle
- remote_inviting
- remote_waiting_approval
- remote_streaming
- remote_controlling
- remote_disconnected

## Client design constraints

- multi-platform from the start at the interface boundary
- Windows first at runtime feature completeness
- UI must tolerate offline and reconnect states
- remote-control UI must stay isolated from normal chat rendering

## Diagrams

- [Client module map](../diagrams/client-module-map.mmd)
- [Desktop navigation flow](../diagrams/client-navigation-flow.mmd)
