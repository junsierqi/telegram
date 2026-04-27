#pragma once

#include "transport/response_messages.h"
#include "transport/request_messages.h"
#include "shared/protocol/control_envelope.h"
#include "shared/protocol/remote_session.h"

#include <cstdint>
#include <cstddef>
#include <optional>
#include <string>

namespace telegram_like::client::transport {

class SessionGatewayClient {
public:
    SessionGatewayClient();
    ~SessionGatewayClient();

    SessionGatewayClient(const SessionGatewayClient&) = delete;
    SessionGatewayClient& operator=(const SessionGatewayClient&) = delete;

    [[nodiscard]] std::string describe() const;
    [[nodiscard]] bool connect(const std::string& host, unsigned short port);
    void disconnect();
    [[nodiscard]] bool is_connected() const;

    [[nodiscard]] std::string compose_request_json(const LoginRequestMessage& message) const;
    [[nodiscard]] std::string compose_request_json(
        const EmptyPayloadRequestMessage& message) const;
    [[nodiscard]] std::string compose_request_json(
        const MessageSendRequestMessage& message) const;
    [[nodiscard]] std::string compose_request_json(
        const RemoteInviteRequestMessage& message) const;
    [[nodiscard]] std::string compose_request_json(
        const RemoteApproveRequestMessage& message) const;
    [[nodiscard]] std::string compose_request_json(
        const RemoteSessionActionRequestMessage& message) const;
    [[nodiscard]] std::string compose_request_json(
        const RemoteDisconnectRequestMessage& message) const;
    [[nodiscard]] std::optional<std::string> send_request_json(const std::string& request_json);
    [[nodiscard]] std::optional<GatewayResponseMessage> parse_response_message(
        const std::string& response_json) const;

private:
    std::uintptr_t socket_ {static_cast<std::uintptr_t>(-1)};
    bool winsock_started_ {false};
};

}  // namespace telegram_like::client::transport
