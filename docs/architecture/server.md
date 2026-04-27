# Server Architecture

## Role

The server is the control-plane backbone written in `Python`. It owns:

- account identity
- authentication
- device registration
- chat session management
- message routing
- persistence
- attachment metadata handling
- online presence
- future remote-session negotiation

For remote control, the server side is intended to support a first-party remote desktop subsystem. It is not a wrapper around a third-party remote-control product.

The server should not be assumed to carry all future high-throughput media streams. Remote-control relay and media forwarding may later move into a separate service better suited to sustained binary throughput.

## Service boundaries

### API and session gateway

- login
- token refresh
- websocket or TCP connection
- session validation
- request dispatch

### Auth service

- credential verification
- token issue and revoke
- device trust
- optional 2FA later

### Chat service

- conversation create and update
- membership changes
- message write path
- message fan-out
- unread state

### Presence service

- online status
- last seen
- active device tracking
- heartbeat processing

### File metadata service

- upload intent
- attachment metadata
- object store key generation
- download authorization

### Remote-session coordination service

- session invite
- approval workflow
- rendezvous and peer discovery
- capability lookup
- relay decision
- audit events

## Storage direction

- relational database for accounts, conversations, messages, devices
- cache for presence and ephemeral session state
- object store for large attachments

## Suggested Python stack

- `FastAPI` or `aiohttp` for APIs
- websocket support for persistent sessions
- `SQLAlchemy` for persistence
- `PostgreSQL` as primary database
- `Redis` for presence and transient coordination

## Current code scaffold

- `server/main.py`
- `server/server/app.py`
- `server/server/services/auth.py`
- `server/server/services/chat.py`
- `server/server/services/presence.py`
- `server/server/services/remote_session.py`

The current implementation is intentionally lightweight and acts as a service-boundary skeleton for the chat MVP control plane.

## Scaling strategy

- keep stateless API/gateway nodes where possible
- put durable state in PostgreSQL
- use Redis for hot session and presence data
- split relay/media later when throughput demands it

The long-term direction is compatible with RustDesk-like separation:

- Python control plane for identity, policy, rendezvous and audit
- separate relay or media services for sustained binary traffic
- dedicated remote-session credentials rather than reusing chat payload channels

## Diagrams

- [Server service map](../diagrams/server-service-map.mmd)
- [Message delivery sequence](../diagrams/message-delivery-sequence.mmd)
