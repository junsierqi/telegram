#pragma once

#include <cstdint>
#include <string>
#include <string_view>

namespace telegram_like::shared::protocol {

// Keep this list in sync with server/server/protocol.py::ErrorCode.
// Ordinal values are for storage; the wire format uses the snake_case name.
enum class ErrorCode : std::uint16_t {
    kUnknown = 0,
    kInvalidCredentials,
    kInvalidSession,
    kSessionActorMismatch,
    kUnsupportedMessageType,
    kUnknownConversation,
    kConversationAccessDenied,
    kEmptyMessage,
    kUnknownRemoteSession,
    kUnknownRequesterDevice,
    kUnknownTargetDevice,
    kRequesterDeviceUserMismatch,
    kRequesterDeviceSessionMismatch,
    kSelfRemoteSessionNotAllowed,
    kRemoteSessionNotAwaitingApproval,
    kRemoteApprovalDenied,
    kRemoteRejectionDenied,
    kRemoteCancelDenied,
    kRemoteTerminateDenied,
    kRemoteDisconnectDenied,
    kRemoteRendezvousDenied,
    kRemoteSessionAlreadyTerminal,
    kRemoteSessionNotActive,
    kRemoteSessionNotReadyForRendezvous
};

[[nodiscard]] constexpr std::string_view to_wire(ErrorCode code) {
    switch (code) {
    case ErrorCode::kUnknown:                           return "unknown";
    case ErrorCode::kInvalidCredentials:                return "invalid_credentials";
    case ErrorCode::kInvalidSession:                    return "invalid_session";
    case ErrorCode::kSessionActorMismatch:              return "session_actor_mismatch";
    case ErrorCode::kUnsupportedMessageType:            return "unsupported_message_type";
    case ErrorCode::kUnknownConversation:               return "unknown_conversation";
    case ErrorCode::kConversationAccessDenied:          return "conversation_access_denied";
    case ErrorCode::kEmptyMessage:                      return "empty_message";
    case ErrorCode::kUnknownRemoteSession:              return "unknown_remote_session";
    case ErrorCode::kUnknownRequesterDevice:            return "unknown_requester_device";
    case ErrorCode::kUnknownTargetDevice:               return "unknown_target_device";
    case ErrorCode::kRequesterDeviceUserMismatch:       return "requester_device_user_mismatch";
    case ErrorCode::kRequesterDeviceSessionMismatch:    return "requester_device_session_mismatch";
    case ErrorCode::kSelfRemoteSessionNotAllowed:       return "self_remote_session_not_allowed";
    case ErrorCode::kRemoteSessionNotAwaitingApproval:  return "remote_session_not_awaiting_approval";
    case ErrorCode::kRemoteApprovalDenied:              return "remote_approval_denied";
    case ErrorCode::kRemoteRejectionDenied:             return "remote_rejection_denied";
    case ErrorCode::kRemoteCancelDenied:                return "remote_cancel_denied";
    case ErrorCode::kRemoteTerminateDenied:             return "remote_terminate_denied";
    case ErrorCode::kRemoteDisconnectDenied:            return "remote_disconnect_denied";
    case ErrorCode::kRemoteRendezvousDenied:            return "remote_rendezvous_denied";
    case ErrorCode::kRemoteSessionAlreadyTerminal:      return "remote_session_already_terminal";
    case ErrorCode::kRemoteSessionNotActive:            return "remote_session_not_active";
    case ErrorCode::kRemoteSessionNotReadyForRendezvous: return "remote_session_not_ready_for_rendezvous";
    }
    return "unknown";
}

[[nodiscard]] inline ErrorCode error_code_from_wire(std::string_view wire) {
    if (wire == "invalid_credentials")                return ErrorCode::kInvalidCredentials;
    if (wire == "invalid_session")                    return ErrorCode::kInvalidSession;
    if (wire == "session_actor_mismatch")             return ErrorCode::kSessionActorMismatch;
    if (wire == "unsupported_message_type")           return ErrorCode::kUnsupportedMessageType;
    if (wire == "unknown_conversation")               return ErrorCode::kUnknownConversation;
    if (wire == "conversation_access_denied")         return ErrorCode::kConversationAccessDenied;
    if (wire == "empty_message")                      return ErrorCode::kEmptyMessage;
    if (wire == "unknown_remote_session")             return ErrorCode::kUnknownRemoteSession;
    if (wire == "unknown_requester_device")           return ErrorCode::kUnknownRequesterDevice;
    if (wire == "unknown_target_device")              return ErrorCode::kUnknownTargetDevice;
    if (wire == "requester_device_user_mismatch")     return ErrorCode::kRequesterDeviceUserMismatch;
    if (wire == "requester_device_session_mismatch")  return ErrorCode::kRequesterDeviceSessionMismatch;
    if (wire == "self_remote_session_not_allowed")    return ErrorCode::kSelfRemoteSessionNotAllowed;
    if (wire == "remote_session_not_awaiting_approval") return ErrorCode::kRemoteSessionNotAwaitingApproval;
    if (wire == "remote_approval_denied")             return ErrorCode::kRemoteApprovalDenied;
    if (wire == "remote_rejection_denied")            return ErrorCode::kRemoteRejectionDenied;
    if (wire == "remote_cancel_denied")               return ErrorCode::kRemoteCancelDenied;
    if (wire == "remote_terminate_denied")            return ErrorCode::kRemoteTerminateDenied;
    if (wire == "remote_disconnect_denied")           return ErrorCode::kRemoteDisconnectDenied;
    if (wire == "remote_rendezvous_denied")           return ErrorCode::kRemoteRendezvousDenied;
    if (wire == "remote_session_already_terminal")    return ErrorCode::kRemoteSessionAlreadyTerminal;
    if (wire == "remote_session_not_active")          return ErrorCode::kRemoteSessionNotActive;
    if (wire == "remote_session_not_ready_for_rendezvous") return ErrorCode::kRemoteSessionNotReadyForRendezvous;
    return ErrorCode::kUnknown;
}

struct ErrorPayload {
    ErrorCode code {ErrorCode::kUnknown};
    std::string message;
};

}  // namespace telegram_like::shared::protocol
