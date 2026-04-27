#pragma once

#include "shared/protocol/control_envelope.h"
#include "shared/protocol/remote_session.h"

#include <string>

namespace telegram_like::client::transport {

struct LoginRequestMessage {
    std::string username;
    std::string password;
    std::string device_id;
    std::string correlation_id;
};

struct EmptyPayloadRequestMessage {
    shared::protocol::ControlEnvelope envelope;
};

struct MessageSendRequestMessage {
    shared::protocol::ControlEnvelope envelope;
    std::string conversation_id;
    std::string text;
};

struct RemoteInviteRequestMessage {
    shared::protocol::ControlEnvelope envelope;
    shared::protocol::RemoteInvitePayload payload;
};

struct RemoteApproveRequestMessage {
    shared::protocol::ControlEnvelope envelope;
    std::string remote_session_id;
};

struct RemoteSessionActionRequestMessage {
    shared::protocol::ControlEnvelope envelope;
    std::string remote_session_id;
};

struct RemoteDisconnectRequestMessage {
    shared::protocol::ControlEnvelope envelope;
    std::string remote_session_id;
    std::string reason;
};

[[nodiscard]] std::string serialize_request(const LoginRequestMessage& message);
[[nodiscard]] std::string serialize_request(const EmptyPayloadRequestMessage& message);
[[nodiscard]] std::string serialize_request(const MessageSendRequestMessage& message);
[[nodiscard]] std::string serialize_request(const RemoteInviteRequestMessage& message);
[[nodiscard]] std::string serialize_request(const RemoteApproveRequestMessage& message);
[[nodiscard]] std::string serialize_request(const RemoteSessionActionRequestMessage& message);
[[nodiscard]] std::string serialize_request(const RemoteDisconnectRequestMessage& message);

}  // namespace telegram_like::client::transport
