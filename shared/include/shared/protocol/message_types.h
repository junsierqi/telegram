#pragma once

#include <cstdint>
#include <string_view>

namespace telegram_like::shared::protocol {

enum class MessageType : std::uint16_t {
    kLoginRequest = 1,
    kLoginResponse = 2,
    kPresenceUpdate = 3,
    kMessageSend = 4,
    kMessageDeliver = 5,
    kAttachmentIntent = 6,
    kAttachmentReady = 7,
    kRemoteInvite = 8,
    kRemoteApprove = 9,
    kHeartbeat = 10,
    kSessionRefresh = 11,
    kConversationSync = 12,
    kMessageAck = 13,
    kDeviceListRequest = 14,
    kDeviceListResponse = 15,
    kRemoteReject = 16,
    kRemoteCancel = 17,
    kRemoteSessionState = 18,
    kRemoteRendezvousInfo = 19,
    kRemoteRelayAssignment = 20,
    kRemoteSessionTerminated = 21,
    kError = 22,
    kRemoteTerminate = 23,
    kRemoteDisconnect = 24,
    kRemoteRendezvousRequest = 25,
    kRemoteInputEvent = 26,
    kRemoteInputAck = 27,
    kMessageForward = 28,
    kMessageReaction = 29,
    kMessageReactionUpdated = 30,
    kMessagePin = 31,
    kMessagePinUpdated = 32,
    kMessageSearchRequest = 33,
    kMessageSearchResponse = 34
};

[[nodiscard]] constexpr std::string_view to_string(MessageType type) {
    switch (type) {
    case MessageType::kLoginRequest:
        return "login_request";
    case MessageType::kLoginResponse:
        return "login_response";
    case MessageType::kPresenceUpdate:
        return "presence_update";
    case MessageType::kMessageSend:
        return "message_send";
    case MessageType::kMessageDeliver:
        return "message_deliver";
    case MessageType::kAttachmentIntent:
        return "attachment_intent";
    case MessageType::kAttachmentReady:
        return "attachment_ready";
    case MessageType::kRemoteInvite:
        return "remote_invite";
    case MessageType::kRemoteApprove:
        return "remote_approve";
    case MessageType::kHeartbeat:
        return "heartbeat";
    case MessageType::kSessionRefresh:
        return "session_refresh";
    case MessageType::kConversationSync:
        return "conversation_sync";
    case MessageType::kMessageAck:
        return "message_ack";
    case MessageType::kDeviceListRequest:
        return "device_list_request";
    case MessageType::kDeviceListResponse:
        return "device_list_response";
    case MessageType::kRemoteReject:
        return "remote_reject";
    case MessageType::kRemoteCancel:
        return "remote_cancel";
    case MessageType::kRemoteSessionState:
        return "remote_session_state";
    case MessageType::kRemoteRendezvousInfo:
        return "remote_rendezvous_info";
    case MessageType::kRemoteRelayAssignment:
        return "remote_relay_assignment";
    case MessageType::kRemoteSessionTerminated:
        return "remote_session_terminated";
    case MessageType::kError:
        return "error";
    case MessageType::kRemoteTerminate:
        return "remote_terminate";
    case MessageType::kRemoteDisconnect:
        return "remote_disconnect";
    case MessageType::kRemoteRendezvousRequest:
        return "remote_rendezvous_request";
    case MessageType::kRemoteInputEvent:
        return "remote_input_event";
    case MessageType::kRemoteInputAck:
        return "remote_input_ack";
    case MessageType::kMessageForward:
        return "message_forward";
    case MessageType::kMessageReaction:
        return "message_reaction";
    case MessageType::kMessageReactionUpdated:
        return "message_reaction_updated";
    case MessageType::kMessagePin:
        return "message_pin";
    case MessageType::kMessagePinUpdated:
        return "message_pin_updated";
    case MessageType::kMessageSearchRequest:
        return "message_search_request";
    case MessageType::kMessageSearchResponse:
        return "message_search_response";
    }

    return "unknown";
}

}  // namespace telegram_like::shared::protocol
