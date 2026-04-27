#pragma once

#include <optional>
#include <string>
#include <variant>
#include <vector>

namespace telegram_like::client::transport {

struct EmptyPayload {};

struct ErrorResponsePayload {
    std::string code;  // snake_case wire form of shared::protocol::ErrorCode
    std::string message;
};

struct LoginResponsePayload {
    std::string session_id;
    std::string user_id;
    std::string display_name;
    std::string device_id;
};

struct DeviceDescriptor {
    std::string device_id;
    std::string label;
    std::string platform;
    bool trusted {false};
    bool active {false};
};

struct DeviceListResponsePayload {
    std::vector<DeviceDescriptor> devices;
};

struct MessageDescriptor {
    std::string message_id;
    std::string sender_user_id;
    std::string text;
};

struct ConversationDescriptor {
    std::string conversation_id;
    std::vector<std::string> participant_user_ids;
    std::vector<MessageDescriptor> messages;
};

struct ConversationSyncResponsePayload {
    std::vector<ConversationDescriptor> conversations;
};

struct MessageDeliverPayload {
    std::string conversation_id;
    std::string message_id;
    std::string sender_user_id;
    std::string text;
};

struct RemoteSessionStatePayload {
    std::string remote_session_id;
    std::string state;
    std::string target_user_id;
    std::string target_device_id;
};

struct RemoteRelayAssignmentPayload {
    std::string remote_session_id;
    std::string state;
    std::string relay_region;
    std::string relay_endpoint;
};

struct RemoteSessionTerminatedPayload {
    std::string remote_session_id;
    std::string state;
    std::string detail;
};

struct RemoteRendezvousCandidate {
    std::string kind;
    std::string address;
    int port {0};
    int priority {0};
};

struct RemoteRendezvousInfoPayload {
    std::string remote_session_id;
    std::string state;
    std::vector<RemoteRendezvousCandidate> candidates;
    std::string relay_region;
    std::string relay_endpoint;
};

using ResponsePayload = std::variant<EmptyPayload,
                                     ErrorResponsePayload,
                                     LoginResponsePayload,
                                     DeviceListResponsePayload,
                                     ConversationSyncResponsePayload,
                                     MessageDeliverPayload,
                                     RemoteSessionStatePayload,
                                     RemoteRelayAssignmentPayload,
                                     RemoteSessionTerminatedPayload,
                                     RemoteRendezvousInfoPayload>;

struct GatewayResponseMessage {
    std::string type;
    std::string session_id;
    std::string actor_user_id;
    ResponsePayload payload;
    std::string raw_json;
};

[[nodiscard]] std::optional<GatewayResponseMessage> parse_response_json(
    const std::string& response_json);

}  // namespace telegram_like::client::transport
