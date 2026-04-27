#pragma once

// Move-only RAII wrapper around NativeSocket. The destructor closes the
// socket if it still owns one. Intentionally minimal — higher-level
// clients should hold a Socket by value and rely on its destructor.

#include "net/platform.h"

#include <utility>

namespace telegram_like::client::net {

class Socket {
public:
    Socket() noexcept : handle_(kInvalidSocket) {}
    explicit Socket(NativeSocket handle) noexcept : handle_(handle) {}

    ~Socket() noexcept { reset(); }

    Socket(const Socket&) = delete;
    Socket& operator=(const Socket&) = delete;

    Socket(Socket&& other) noexcept : handle_(other.handle_) {
        other.handle_ = kInvalidSocket;
    }
    Socket& operator=(Socket&& other) noexcept {
        if (this != &other) {
            reset();
            handle_ = other.handle_;
            other.handle_ = kInvalidSocket;
        }
        return *this;
    }

    [[nodiscard]] bool valid() const noexcept { return is_valid(handle_); }
    [[nodiscard]] NativeSocket get() const noexcept { return handle_; }

    // Release ownership of the underlying handle without closing it.
    [[nodiscard]] NativeSocket release() noexcept {
        NativeSocket h = handle_;
        handle_ = kInvalidSocket;
        return h;
    }

    // Close any held handle and take ownership of a new one.
    void reset(NativeSocket handle = kInvalidSocket) noexcept {
        if (is_valid(handle_)) {
            close_native_socket(handle_);
        }
        handle_ = handle;
    }

private:
    NativeSocket handle_;
};

}  // namespace telegram_like::client::net
