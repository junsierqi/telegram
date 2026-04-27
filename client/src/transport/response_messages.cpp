#include "transport/response_messages.h"

#include "transport/json_value.h"

#include <string_view>

namespace telegram_like::client::transport {

namespace {

bool bool_or_false(const JsonObject& object, std::string_view key) {
    const auto* value = find_member(object, key);
    if (value == nullptr) {
        return false;
    }
    const auto* bool_value = std::get_if<bool>(&value->storage);
    return bool_value != nullptr && *bool_value;
}

int int_or_zero(const JsonObject& object, std::string_view key) {
    const auto* value = find_member(object, key);
    if (value == nullptr) {
        return 0;
    }
    const auto* number_value = std::get_if<double>(&value->storage);
    return number_value != nullptr ? static_cast<int>(*number_value) : 0;
}

std::vector<std::string> string_array_or_empty(const JsonObject& object, std::string_view key) {
    std::vector<std::string> values;
    const auto* value = find_member(object, key);
    if (value == nullptr) {
        return values;
    }
    const auto* array = value->as_array();
    if (array == nullptr) {
        return values;
    }
    values.reserve(array->size());
    for (const auto& item : *array) {
        if (const auto* string_value = item.as_string(); string_value != nullptr) {
            values.push_back(*string_value);
        }
    }
    return values;
}

std::vector<MessageDescriptor> parse_messages(const JsonObject& conversation) {
    std::vector<MessageDescriptor> messages;
    const auto* messages_value = find_member(conversation, "messages");
    if (messages_value == nullptr) {
        return messages;
    }
    const auto* message_array = messages_value->as_array();
    if (message_array == nullptr) {
        return messages;
    }

    messages.reserve(message_array->size());
    for (const auto& item : *message_array) {
        const auto* message_object = item.as_object();
        if (message_object == nullptr) {
            continue;
        }
        messages.push_back(MessageDescriptor {
            .message_id = string_or_empty(*message_object, "message_id"),
            .sender_user_id = string_or_empty(*message_object, "sender_user_id"),
            .text = string_or_empty(*message_object, "text"),
        });
    }
    return messages;
}

ResponsePayload parse_payload(const std::string& type, const JsonObject* payload_object) {
    if (payload_object == nullptr) {
        return EmptyPayload {};
    }

    if (type == "error") {
        return ErrorResponsePayload {
            .code = string_or_empty(*payload_object, "code"),
            .message = string_or_empty(*payload_object, "message"),
        };
    }
    if (type == "login_response") {
        return LoginResponsePayload {
            .session_id = string_or_empty(*payload_object, "session_id"),
            .user_id = string_or_empty(*payload_object, "user_id"),
            .display_name = string_or_empty(*payload_object, "display_name"),
            .device_id = string_or_empty(*payload_object, "device_id"),
        };
    }
    if (type == "device_list_response") {
        DeviceListResponsePayload payload;
        const auto* devices_value = find_member(*payload_object, "devices");
        const auto* devices = devices_value != nullptr ? devices_value->as_array() : nullptr;
        if (devices != nullptr) {
            payload.devices.reserve(devices->size());
            for (const auto& item : *devices) {
                const auto* device = item.as_object();
                if (device == nullptr) {
                    continue;
                }
                payload.devices.push_back(DeviceDescriptor {
                    .device_id = string_or_empty(*device, "device_id"),
                    .label = string_or_empty(*device, "label"),
                    .platform = string_or_empty(*device, "platform"),
                    .trusted = bool_or_false(*device, "trusted"),
                    .active = bool_or_false(*device, "active"),
                });
            }
        }
        return payload;
    }
    if (type == "conversation_sync") {
        ConversationSyncResponsePayload payload;
        const auto* conversations_value = find_member(*payload_object, "conversations");
        const auto* conversations =
            conversations_value != nullptr ? conversations_value->as_array() : nullptr;
        if (conversations != nullptr) {
            payload.conversations.reserve(conversations->size());
            for (const auto& item : *conversations) {
                const auto* conversation = item.as_object();
                if (conversation == nullptr) {
                    continue;
                }
                payload.conversations.push_back(ConversationDescriptor {
                    .conversation_id = string_or_empty(*conversation, "conversation_id"),
                    .participant_user_ids =
                        string_array_or_empty(*conversation, "participant_user_ids"),
                    .messages = parse_messages(*conversation),
                });
            }
        }
        return payload;
    }
    if (type == "message_deliver") {
        return MessageDeliverPayload {
            .conversation_id = string_or_empty(*payload_object, "conversation_id"),
            .message_id = string_or_empty(*payload_object, "message_id"),
            .sender_user_id = string_or_empty(*payload_object, "sender_user_id"),
            .text = string_or_empty(*payload_object, "text"),
        };
    }
    if (type == "remote_session_state") {
        return RemoteSessionStatePayload {
            .remote_session_id = string_or_empty(*payload_object, "remote_session_id"),
            .state = string_or_empty(*payload_object, "state"),
            .target_user_id = string_or_empty(*payload_object, "target_user_id"),
            .target_device_id = string_or_empty(*payload_object, "target_device_id"),
        };
    }
    if (type == "remote_relay_assignment") {
        return RemoteRelayAssignmentPayload {
            .remote_session_id = string_or_empty(*payload_object, "remote_session_id"),
            .state = string_or_empty(*payload_object, "state"),
            .relay_region = string_or_empty(*payload_object, "relay_region"),
            .relay_endpoint = string_or_empty(*payload_object, "relay_endpoint"),
        };
    }
    if (type == "remote_session_terminated") {
        return RemoteSessionTerminatedPayload {
            .remote_session_id = string_or_empty(*payload_object, "remote_session_id"),
            .state = string_or_empty(*payload_object, "state"),
            .detail = string_or_empty(*payload_object, "detail"),
        };
    }
    if (type == "remote_rendezvous_info") {
        std::vector<RemoteRendezvousCandidate> candidates;
        const auto* candidates_value = find_member(*payload_object, "candidates");
        if (candidates_value != nullptr) {
            if (const auto* array = candidates_value->as_array(); array != nullptr) {
                candidates.reserve(array->size());
                for (const auto& item : *array) {
                    const auto* candidate_object = item.as_object();
                    if (candidate_object == nullptr) {
                        continue;
                    }
                    candidates.push_back(RemoteRendezvousCandidate {
                        .kind = string_or_empty(*candidate_object, "kind"),
                        .address = string_or_empty(*candidate_object, "address"),
                        .port = int_or_zero(*candidate_object, "port"),
                        .priority = int_or_zero(*candidate_object, "priority"),
                    });
                }
            }
        }
        return RemoteRendezvousInfoPayload {
            .remote_session_id = string_or_empty(*payload_object, "remote_session_id"),
            .state = string_or_empty(*payload_object, "state"),
            .candidates = std::move(candidates),
            .relay_region = string_or_empty(*payload_object, "relay_region"),
            .relay_endpoint = string_or_empty(*payload_object, "relay_endpoint"),
        };
    }

    return EmptyPayload {};
}

}  // namespace

std::optional<GatewayResponseMessage> parse_response_json(const std::string& response_json) {
    JsonValue root;
    JsonParser parser {response_json};
    if (!parser.parse(root)) {
        return std::nullopt;
    }

    const auto* root_object = root.as_object();
    if (root_object == nullptr) {
        return std::nullopt;
    }

    const auto type = string_or_empty(*root_object, "type");
    const auto* payload_value = find_member(*root_object, "payload");
    const auto* payload_object = payload_value != nullptr ? payload_value->as_object() : nullptr;

    return GatewayResponseMessage {
        .type = type,
        .session_id = string_or_empty(*root_object, "session_id"),
        .actor_user_id = string_or_empty(*root_object, "actor_user_id"),
        .payload = parse_payload(type, payload_object),
        .raw_json = response_json,
    };
}

}  // namespace telegram_like::client::transport
