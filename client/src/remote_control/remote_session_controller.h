#pragma once

#include "shared/protocol/remote_session.h"

#include <string>

namespace telegram_like::client::remote_control {

class RemoteSessionController {
public:
    RemoteSessionController() = default;

    [[nodiscard]] std::string describe() const;
    [[nodiscard]] telegram_like::shared::protocol::RemoteSessionState state() const;
    [[nodiscard]] bool apply_event(telegram_like::shared::protocol::RemoteSessionEvent event);

private:
    telegram_like::shared::protocol::RemoteSessionState state_ {
        telegram_like::shared::protocol::RemoteSessionState::kIdle};
};

}  // namespace telegram_like::client::remote_control
