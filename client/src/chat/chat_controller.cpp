#include "chat/chat_controller.h"

namespace telegram_like::client::chat {

std::string ChatController::describe() const {
    return "chat controller ready for conversation sync, message send and attachment flow";
}

}  // namespace telegram_like::client::chat
