#pragma once

#include <string>

namespace telegram_like::client::contacts {

class ContactController {
public:
    [[nodiscard]] std::string describe() const;
};

}  // namespace telegram_like::client::contacts
