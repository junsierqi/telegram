#pragma once

#include <string>

namespace telegram_like::client::auth {

class AuthController {
public:
    [[nodiscard]] std::string describe() const;
};

}  // namespace telegram_like::client::auth
