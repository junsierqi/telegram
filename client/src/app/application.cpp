#include "app/application.h"

#include "app/app_shell.h"

namespace telegram_like::client::app {

int Application::run() const {
    return AppShell {}.start();
}

}  // namespace telegram_like::client::app
