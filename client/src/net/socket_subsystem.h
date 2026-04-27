#pragma once

// Scoped socket-subsystem initialiser.
//
// On Windows, wraps WSAStartup / WSACleanup with a process-wide refcount
// so multiple independent clients can each `initialize()` without stepping
// on each other. On POSIX, this is a no-op.

#include "net/platform.h"

namespace telegram_like::client::net {

class SocketSubsystem {
public:
    SocketSubsystem();
    ~SocketSubsystem();

    SocketSubsystem(const SocketSubsystem&) = delete;
    SocketSubsystem& operator=(const SocketSubsystem&) = delete;
    SocketSubsystem(SocketSubsystem&&) = delete;
    SocketSubsystem& operator=(SocketSubsystem&&) = delete;

    [[nodiscard]] bool ok() const noexcept { return ok_; }

private:
    bool ok_;
};

}  // namespace telegram_like::client::net
