#include "transport/request_messages.h"

#include "shared/protocol/message_types.h"

#include <sstream>
#include <string_view>

namespace telegram_like::client::transport {

namespace {

std::string json_escape(std::string_view value) {
    std::string escaped;
    escaped.reserve(value.size());
    for (const char ch : value) {
        switch (ch) {
        case '\\':
            escaped += "\\\\";
            break;
        case '"':
            escaped += "\\\"";
            break;
        case '\n':
            escaped += "\\n";
            break;
        default:
            escaped += ch;
            break;
        }
    }
    return escaped;
}

void write_envelope(std::ostringstream& stream,
                    const shared::protocol::ControlEnvelope& envelope) {
    stream << "\"type\":\"" << shared::protocol::to_string(envelope.type) << "\","
           << "\"correlation_id\":\"" << json_escape(envelope.correlation_id) << "\","
           << "\"session_id\":\"" << json_escape(envelope.session_id) << "\","
           << "\"actor_user_id\":\"" << json_escape(envelope.actor_user_id) << "\","
           << "\"sequence\":" << envelope.sequence;
}

}  // namespace

std::string serialize_request(const LoginRequestMessage& message) {
    std::ostringstream stream;
    stream << "{"
           << "\"type\":\"login_request\","
           << "\"correlation_id\":\"" << json_escape(message.correlation_id) << "\","
           << "\"session_id\":\"\","
           << "\"actor_user_id\":\"\","
           << "\"sequence\":1,"
           << "\"payload\":{"
           << "\"username\":\"" << json_escape(message.username) << "\","
           << "\"password\":\"" << json_escape(message.password) << "\","
           << "\"device_id\":\"" << json_escape(message.device_id) << "\""
           << "}"
           << "}";
    return stream.str();
}

std::string serialize_request(const EmptyPayloadRequestMessage& message) {
    std::ostringstream stream;
    stream << "{";
    write_envelope(stream, message.envelope);
    stream << ",\"payload\":{}}";
    return stream.str();
}

std::string serialize_request(const MessageSendRequestMessage& message) {
    std::ostringstream stream;
    stream << "{";
    write_envelope(stream, message.envelope);
    stream << ",\"payload\":{"
           << "\"conversation_id\":\"" << json_escape(message.conversation_id) << "\","
           << "\"text\":\"" << json_escape(message.text) << "\""
           << "}}";
    return stream.str();
}

std::string serialize_request(const RemoteInviteRequestMessage& message) {
    std::ostringstream stream;
    stream << "{";
    write_envelope(stream, message.envelope);
    stream << ",\"payload\":{"
           << "\"session_id\":\"" << json_escape(message.payload.session_id) << "\","
           << "\"requester_device_id\":\"" << json_escape(message.payload.requester_device_id)
           << "\","
           << "\"target_device_id\":\"" << json_escape(message.payload.target_device_id) << "\","
           << "\"attended_session\":"
           << (message.payload.attended_session ? "true" : "false")
           << "}}";
    return stream.str();
}

std::string serialize_request(const RemoteApproveRequestMessage& message) {
    std::ostringstream stream;
    stream << "{";
    write_envelope(stream, message.envelope);
    stream << ",\"payload\":{"
           << "\"remote_session_id\":\"" << json_escape(message.remote_session_id) << "\""
           << "}}";
    return stream.str();
}

std::string serialize_request(const RemoteSessionActionRequestMessage& message) {
    std::ostringstream stream;
    stream << "{";
    write_envelope(stream, message.envelope);
    stream << ",\"payload\":{"
           << "\"remote_session_id\":\"" << json_escape(message.remote_session_id) << "\""
           << "}}";
    return stream.str();
}

std::string serialize_request(const RemoteDisconnectRequestMessage& message) {
    std::ostringstream stream;
    stream << "{";
    write_envelope(stream, message.envelope);
    stream << ",\"payload\":{"
           << "\"remote_session_id\":\"" << json_escape(message.remote_session_id) << "\","
           << "\"reason\":\"" << json_escape(message.reason) << "\""
           << "}}";
    return stream.str();
}

}  // namespace telegram_like::client::transport
