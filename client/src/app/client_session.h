#pragma once

#include "shared/protocol/control_envelope.h"
#include "shared/protocol/message_types.h"

#include <string>

namespace telegram_like::client::app {

struct ClientSession {
    std::string username;
    std::string device_id;
    std::string user_id;
    std::string session_id;
    std::uint64_t next_sequence {1};

    [[nodiscard]] shared::protocol::ControlEnvelope make_envelope(
        const shared::protocol::MessageType type,
        std::string correlation_id) {
        return shared::protocol::ControlEnvelope {
            .type = type,
            .correlation_id = std::move(correlation_id),
            .session_id = session_id,
            .actor_user_id = user_id,
            .sequence = next_sequence++,
        };
    }
};

}  // namespace telegram_like::client::app
