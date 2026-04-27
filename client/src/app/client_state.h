#pragma once

#include "transport/response_messages.h"

#include <cstddef>
#include <variant>
#include <string>

namespace telegram_like::client::app {

struct ChatState {
    std::size_t device_count {0};
    std::size_t conversation_count {0};
    std::size_t conversation_message_count {0};
    std::string last_message_id;

    void apply_response(const transport::GatewayResponseMessage& response) {
        if (const auto* device_list =
                std::get_if<transport::DeviceListResponsePayload>(&response.payload);
            device_list != nullptr) {
            device_count = device_list->devices.size();
        }
        if (const auto* conversation_sync =
                std::get_if<transport::ConversationSyncResponsePayload>(&response.payload);
            conversation_sync != nullptr) {
            conversation_count = conversation_sync->conversations.size();
            conversation_message_count = 0;
            for (const auto& conversation : conversation_sync->conversations) {
                conversation_message_count += conversation.messages.size();
            }
        }
        if (const auto* delivered =
                std::get_if<transport::MessageDeliverPayload>(&response.payload);
            delivered != nullptr) {
            last_message_id = delivered->message_id;
        }
    }
};

struct RemoteControlState {
    std::string remote_session_id;
    std::string remote_session_state;
    std::string relay_region;
    std::string relay_endpoint;
    std::size_t candidate_count {0};

    void apply_response(const transport::GatewayResponseMessage& response) {
        if (const auto* state =
                std::get_if<transport::RemoteSessionStatePayload>(&response.payload);
            state != nullptr) {
            remote_session_id = state->remote_session_id;
            remote_session_state = state->state;
        }
        if (const auto* relay =
                std::get_if<transport::RemoteRelayAssignmentPayload>(&response.payload);
            relay != nullptr) {
            remote_session_id = relay->remote_session_id;
            remote_session_state = relay->state;
            relay_region = relay->relay_region;
            relay_endpoint = relay->relay_endpoint;
        }
        if (const auto* rendezvous =
                std::get_if<transport::RemoteRendezvousInfoPayload>(&response.payload);
            rendezvous != nullptr) {
            remote_session_id = rendezvous->remote_session_id;
            remote_session_state = rendezvous->state;
            relay_region = rendezvous->relay_region;
            relay_endpoint = rendezvous->relay_endpoint;
            candidate_count = rendezvous->candidates.size();
        }
        if (const auto* terminated =
                std::get_if<transport::RemoteSessionTerminatedPayload>(&response.payload);
            terminated != nullptr) {
            remote_session_id = terminated->remote_session_id;
            remote_session_state = terminated->state;
            relay_region.clear();
            relay_endpoint.clear();
            candidate_count = 0;
        }
    }
};

struct ClientViewState {
    std::string current_session_id;
    std::string current_user_id;
    ChatState chat;
    RemoteControlState remote;
    std::string last_error_code;
    std::string last_error_message;

    void apply_response(const transport::GatewayResponseMessage& response) {
        chat.apply_response(response);
        remote.apply_response(response);
        if (const auto* error = std::get_if<transport::ErrorResponsePayload>(&response.payload);
            error != nullptr) {
            last_error_code = error->code;
            last_error_message = error->message;
        }
    }
};

}  // namespace telegram_like::client::app
