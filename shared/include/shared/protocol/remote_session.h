#pragma once

#include <array>
#include <cstdint>
#include <string>
#include <string_view>

namespace telegram_like::shared::protocol {

enum class RemoteSessionState : std::uint8_t {
    kIdle = 0,
    kInviting = 1,
    kAwaitingApproval = 2,
    kApproved = 3,
    kNegotiating = 4,
    kConnecting = 5,
    kStreaming = 6,
    kControlling = 7,
    kRejected = 8,
    kCancelled = 9,
    kDisconnected = 10,
    kTerminated = 11
};

[[nodiscard]] constexpr std::string_view to_string(RemoteSessionState state) {
    switch (state) {
    case RemoteSessionState::kIdle:
        return "idle";
    case RemoteSessionState::kInviting:
        return "inviting";
    case RemoteSessionState::kAwaitingApproval:
        return "awaiting_approval";
    case RemoteSessionState::kApproved:
        return "approved";
    case RemoteSessionState::kNegotiating:
        return "negotiating";
    case RemoteSessionState::kConnecting:
        return "connecting";
    case RemoteSessionState::kStreaming:
        return "streaming";
    case RemoteSessionState::kControlling:
        return "controlling";
    case RemoteSessionState::kRejected:
        return "rejected";
    case RemoteSessionState::kCancelled:
        return "cancelled";
    case RemoteSessionState::kDisconnected:
        return "disconnected";
    case RemoteSessionState::kTerminated:
        return "terminated";
    }

    return "unknown";
}

enum class RemoteSessionEvent : std::uint8_t {
    kSendInvite = 0,
    kReceiveInvite = 1,
    kApprove = 2,
    kReject = 3,
    kCancel = 4,
    kBeginNegotiation = 5,
    kConnectTransport = 6,
    kStartStream = 7,
    kGainInputControl = 8,
    kDropTransport = 9,
    kTerminate = 10
};

[[nodiscard]] constexpr std::string_view to_string(RemoteSessionEvent event) {
    switch (event) {
    case RemoteSessionEvent::kSendInvite:
        return "send_invite";
    case RemoteSessionEvent::kReceiveInvite:
        return "receive_invite";
    case RemoteSessionEvent::kApprove:
        return "approve";
    case RemoteSessionEvent::kReject:
        return "reject";
    case RemoteSessionEvent::kCancel:
        return "cancel";
    case RemoteSessionEvent::kBeginNegotiation:
        return "begin_negotiation";
    case RemoteSessionEvent::kConnectTransport:
        return "connect_transport";
    case RemoteSessionEvent::kStartStream:
        return "start_stream";
    case RemoteSessionEvent::kGainInputControl:
        return "gain_input_control";
    case RemoteSessionEvent::kDropTransport:
        return "drop_transport";
    case RemoteSessionEvent::kTerminate:
        return "terminate";
    }

    return "unknown";
}

struct DeviceCapability {
    std::string device_id;
    std::string platform;
    bool can_host {false};
    bool can_view {false};
    bool supports_input_injection {false};
    bool supports_audio {false};
    bool supports_clipboard {false};
};

struct RemoteInvitePayload {
    std::string session_id;
    std::string requester_device_id;
    std::string target_device_id;
    bool attended_session {true};
};

struct RemoteSessionStatusPayload {
    std::string session_id;
    RemoteSessionState state {RemoteSessionState::kIdle};
    std::string detail;
};

struct RelayAssignmentPayload {
    std::string session_id;
    std::string relay_region;
    std::string relay_endpoint;
    bool direct_path_preferred {true};
};

[[nodiscard]] constexpr bool is_terminal(RemoteSessionState state) {
    return state == RemoteSessionState::kRejected ||
           state == RemoteSessionState::kCancelled ||
           state == RemoteSessionState::kDisconnected ||
           state == RemoteSessionState::kTerminated;
}

[[nodiscard]] constexpr RemoteSessionState next_state(RemoteSessionState current,
                                                      RemoteSessionEvent event) {
    switch (event) {
    case RemoteSessionEvent::kSendInvite:
        return current == RemoteSessionState::kIdle ? RemoteSessionState::kInviting : current;
    case RemoteSessionEvent::kReceiveInvite:
        return current == RemoteSessionState::kIdle ? RemoteSessionState::kAwaitingApproval : current;
    case RemoteSessionEvent::kApprove:
        return (current == RemoteSessionState::kInviting ||
                current == RemoteSessionState::kAwaitingApproval)
                   ? RemoteSessionState::kApproved
                   : current;
    case RemoteSessionEvent::kReject:
        return is_terminal(current) ? current : RemoteSessionState::kRejected;
    case RemoteSessionEvent::kCancel:
        return is_terminal(current) ? current : RemoteSessionState::kCancelled;
    case RemoteSessionEvent::kBeginNegotiation:
        return current == RemoteSessionState::kApproved ? RemoteSessionState::kNegotiating : current;
    case RemoteSessionEvent::kConnectTransport:
        return current == RemoteSessionState::kNegotiating ? RemoteSessionState::kConnecting : current;
    case RemoteSessionEvent::kStartStream:
        return current == RemoteSessionState::kConnecting ? RemoteSessionState::kStreaming : current;
    case RemoteSessionEvent::kGainInputControl:
        return current == RemoteSessionState::kStreaming ? RemoteSessionState::kControlling : current;
    case RemoteSessionEvent::kDropTransport:
        return is_terminal(current) ? current : RemoteSessionState::kDisconnected;
    case RemoteSessionEvent::kTerminate:
        return RemoteSessionState::kTerminated;
    }

    return current;
}

}  // namespace telegram_like::shared::protocol
