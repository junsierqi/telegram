#pragma once

// Map native socket errors to a cross-platform enum.

#include "net/platform.h"

#include <string>

namespace telegram_like::client::net {

enum class NetErrorCode {
    kOk = 0,
    kWouldBlock,
    kTimeout,
    kConnectionRefused,
    kConnectionReset,
    kHostUnreachable,
    kNetworkUnreachable,
    kAddressInUse,
    kAddressNotAvailable,
    kInterrupted,
    kNotConnected,
    kShutdown,
    kDnsFailure,
    kPermissionDenied,
    kUnknown,
};

// Returns the last socket error code in platform-agnostic form.
[[nodiscard]] int last_native_error() noexcept;

// Map a platform-native errno/WSAError to our enum.
[[nodiscard]] NetErrorCode map_native_error(int native_error) noexcept;

// Shortcut: take the last native error and map it.
[[nodiscard]] inline NetErrorCode last_error() noexcept {
    return map_native_error(last_native_error());
}

// Human-readable name of the code (stable strings; do not localize).
[[nodiscard]] std::string describe(NetErrorCode code);

}  // namespace telegram_like::client::net
