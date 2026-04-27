# Sequence Flows

## Core system sequences

### Login

Client authenticates, receives tokens, restores local state and opens the main shell.

### Message delivery

Sender posts a message through the gateway, message is stored, routed and delivered to recipient devices, then acknowledged back into conversation state.

### Attachment handling

Client requests upload intent, uploads binary data to object storage, submits metadata, then sends the message referencing the attachment.

### Future remote-control session

Requester sends invite, target approves, server negotiates path, then control and media channels come up outside normal chat message transport.

## Diagram references

- [Message delivery sequence](../diagrams/message-delivery-sequence.mmd)
- [Attachment flow sequence](../diagrams/attachment-sequence.mmd)
- [Remote session sequence](../diagrams/remote-session-sequence.mmd)
