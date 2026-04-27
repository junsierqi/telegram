#pragma once

#include <string>

namespace telegram_like::client::chat {

class ChatController {
public:
    [[nodiscard]] std::string describe() const;
};

}  // namespace telegram_like::client::chat
