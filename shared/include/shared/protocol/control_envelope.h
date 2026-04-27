#pragma once

#include <cstdint>
#include <string>

#include "shared/protocol/message_types.h"

namespace telegram_like::shared::protocol {

struct ControlEnvelope {
    MessageType type {};
    std::string correlation_id;
    std::string session_id;
    std::string actor_user_id;
    std::uint64_t sequence {0};
};

}  // namespace telegram_like::shared::protocol
