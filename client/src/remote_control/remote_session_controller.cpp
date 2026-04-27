#include "remote_control/remote_session_controller.h"

#include <string_view>

namespace telegram_like::client::remote_control {

std::string RemoteSessionController::describe() const {
    using telegram_like::shared::protocol::to_string;

    return "remote-control controller state=" + std::string(to_string(state_)) +
           " with first-party session orchestration for invite, approval and stream states";
}

telegram_like::shared::protocol::RemoteSessionState RemoteSessionController::state() const {
    return state_;
}

bool RemoteSessionController::apply_event(
    telegram_like::shared::protocol::RemoteSessionEvent event) {
    const auto next =
        telegram_like::shared::protocol::next_state(state_, event);
    const bool changed = next != state_;
    state_ = next;
    return changed;
}

}  // namespace telegram_like::client::remote_control
