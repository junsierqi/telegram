#include "transport/session_gateway_client.h"

#include "net/platform.h"
#include "net/socket_error.h"
#include "net/socket_raii.h"
#include "net/socket_subsystem.h"
#include "transport/request_messages.h"
#include "transport/response_messages.h"
#include "shared/protocol/message_types.h"

#include <array>
#include <optional>

namespace telegram_like::client::transport {

namespace {

net::SocketSubsystem& shared_subsystem() {
    static net::SocketSubsystem instance;
    return instance;
}

}  // namespace

SessionGatewayClient::SessionGatewayClient() {
    winsock_started_ = shared_subsystem().ok();
}

SessionGatewayClient::~SessionGatewayClient() {
    disconnect();
    // SocketSubsystem is a shared static — no explicit cleanup here.
}

std::string SessionGatewayClient::describe() const {
    return "session gateway client uses persistent TCP control messages such as " +
           std::string(telegram_like::shared::protocol::to_string(
               telegram_like::shared::protocol::MessageType::kLoginRequest));
}

bool SessionGatewayClient::connect(const std::string& host, const unsigned short port) {
    disconnect();
    if (!winsock_started_) {
        return false;
    }

    addrinfo hints {};
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;

    addrinfo* address_info = nullptr;
    const auto port_text = std::to_string(port);
    if (::getaddrinfo(host.c_str(), port_text.c_str(), &hints, &address_info) != 0) {
        return false;
    }

    for (addrinfo* current = address_info; current != nullptr; current = current->ai_next) {
        const net::NativeSocket candidate =
            ::socket(current->ai_family, current->ai_socktype, current->ai_protocol);
        if (!net::is_valid(candidate)) {
            continue;
        }
        if (::connect(candidate, current->ai_addr,
                      static_cast<net::socklen_type>(current->ai_addrlen)) == 0) {
            socket_ = static_cast<std::uintptr_t>(candidate);
            break;
        }
        net::close_native_socket(candidate);
    }
    ::freeaddrinfo(address_info);

    return is_connected();
}

void SessionGatewayClient::disconnect() {
    if (!is_connected()) {
        socket_ = static_cast<std::uintptr_t>(net::kInvalidSocket);
        return;
    }
    net::close_native_socket(static_cast<net::NativeSocket>(socket_));
    socket_ = static_cast<std::uintptr_t>(net::kInvalidSocket);
}

bool SessionGatewayClient::is_connected() const {
    return net::is_valid(static_cast<net::NativeSocket>(socket_));
}

std::string SessionGatewayClient::compose_request_json(const LoginRequestMessage& message) const {
    return serialize_request(message);
}

std::string SessionGatewayClient::compose_request_json(
    const EmptyPayloadRequestMessage& message) const {
    return serialize_request(message);
}

std::string SessionGatewayClient::compose_request_json(
    const MessageSendRequestMessage& message) const {
    return serialize_request(message);
}

std::string SessionGatewayClient::compose_request_json(
    const RemoteInviteRequestMessage& message) const {
    return serialize_request(message);
}

std::string SessionGatewayClient::compose_request_json(
    const RemoteApproveRequestMessage& message) const {
    return serialize_request(message);
}

std::string SessionGatewayClient::compose_request_json(
    const RemoteSessionActionRequestMessage& message) const {
    return serialize_request(message);
}

std::string SessionGatewayClient::compose_request_json(
    const RemoteDisconnectRequestMessage& message) const {
    return serialize_request(message);
}

std::optional<std::string> SessionGatewayClient::send_request_json(const std::string& request_json) {
    if (!is_connected()) {
        return std::nullopt;
    }

    const net::NativeSocket sock = static_cast<net::NativeSocket>(socket_);
    const std::string request_with_newline = request_json + "\n";
    const long long sent = net::native_send(sock,
                                            request_with_newline.data(),
                                            request_with_newline.size());
    if (sent == net::kSocketError) {
        disconnect();
        return std::nullopt;
    }

    std::string response;
    std::array<char, 1024> buffer {};
    while (true) {
        const long long received = net::native_recv(sock, buffer.data(), buffer.size());
        if (received <= 0) {
            disconnect();
            return std::nullopt;
        }
        response.append(buffer.data(), static_cast<std::size_t>(received));
        if (response.find('\n') != std::string::npos) {
            break;
        }
    }

    const auto newline = response.find('\n');
    if (newline != std::string::npos) {
        response.resize(newline);
    }
    if (response.empty()) {
        return std::nullopt;
    }

    return response;
}

std::optional<GatewayResponseMessage> SessionGatewayClient::parse_response_message(
    const std::string& response_json) const {
    return parse_response_json(response_json);
}

}  // namespace telegram_like::client::transport
