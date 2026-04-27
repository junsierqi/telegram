#include "auth/auth_controller.h"

namespace telegram_like::client::auth {

std::string AuthController::describe() const {
    return "auth controller ready for sign-in, token refresh and session restore";
}

}  // namespace telegram_like::client::auth
