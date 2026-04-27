#pragma once

// Cross-platform socket primitives for the telegram-like client.
//
// All networking code in client/src/transport/** should go through the
// `net` namespace so future Linux/macOS/Android/iOS ports only need to
// extend the platform-specific #ifdef branches below.
//
// Windows branch is tested. POSIX branch is structurally correct but
// not yet exercised by any CI — the first real port will validate it.

#include <cstddef>
#include <cstdint>
#include <string>

#if defined(_WIN32)

#ifndef WIN32_LEAN_AND_MEAN
#define WIN32_LEAN_AND_MEAN
#endif
// Must come before any <windows.h> inclusion.
#include <WinSock2.h>
#include <WS2tcpip.h>

#pragma comment(lib, "ws2_32.lib")

#else  // POSIX

#include <arpa/inet.h>
#include <errno.h>
#include <fcntl.h>
#include <netdb.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <sys/types.h>
#include <unistd.h>

#endif

namespace telegram_like::client::net {

#if defined(_WIN32)
using NativeSocket = ::SOCKET;
inline constexpr NativeSocket kInvalidSocket = static_cast<NativeSocket>(INVALID_SOCKET);
inline constexpr int kSocketError = SOCKET_ERROR;
using socklen_type = int;
#else
using NativeSocket = int;
inline constexpr NativeSocket kInvalidSocket = -1;
inline constexpr int kSocketError = -1;
using socklen_type = ::socklen_t;
#endif

[[nodiscard]] inline bool is_valid(NativeSocket s) noexcept {
    return s != kInvalidSocket;
}

// Close a socket in a platform-agnostic way. Returns 0 on success.
inline int close_native_socket(NativeSocket s) noexcept {
    if (!is_valid(s)) {
        return 0;
    }
#if defined(_WIN32)
    return ::closesocket(s);
#else
    return ::close(s);
#endif
}

// Set a SO_RCVTIMEO timeout on the socket. 0 disables.
inline int set_recv_timeout_ms(NativeSocket s, unsigned timeout_ms) noexcept {
#if defined(_WIN32)
    DWORD value = static_cast<DWORD>(timeout_ms);
    return ::setsockopt(s, SOL_SOCKET, SO_RCVTIMEO,
                        reinterpret_cast<const char*>(&value), sizeof(value));
#else
    struct timeval tv {};
    tv.tv_sec = static_cast<time_t>(timeout_ms / 1000);
    tv.tv_usec = static_cast<suseconds_t>((timeout_ms % 1000) * 1000);
    return ::setsockopt(s, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof(tv));
#endif
}

// send(2) result on Windows is int, on POSIX ssize_t. Normalize to long long.
inline long long native_send(NativeSocket s, const void* buf, std::size_t len) noexcept {
#if defined(_WIN32)
    return ::send(s, reinterpret_cast<const char*>(buf), static_cast<int>(len), 0);
#else
    return static_cast<long long>(::send(s, buf, len, 0));
#endif
}

inline long long native_recv(NativeSocket s, void* buf, std::size_t len) noexcept {
#if defined(_WIN32)
    return ::recv(s, reinterpret_cast<char*>(buf), static_cast<int>(len), 0);
#else
    return static_cast<long long>(::recv(s, buf, len, 0));
#endif
}

inline long long native_sendto(NativeSocket s, const void* buf, std::size_t len,
                               const struct sockaddr* addr, socklen_type addr_len) noexcept {
#if defined(_WIN32)
    return ::sendto(s, reinterpret_cast<const char*>(buf), static_cast<int>(len), 0,
                    addr, addr_len);
#else
    return static_cast<long long>(::sendto(s, buf, len, 0, addr, addr_len));
#endif
}

inline long long native_recvfrom(NativeSocket s, void* buf, std::size_t len,
                                 struct sockaddr* addr, socklen_type* addr_len) noexcept {
#if defined(_WIN32)
    return ::recvfrom(s, reinterpret_cast<char*>(buf), static_cast<int>(len), 0,
                      addr, addr_len);
#else
    return static_cast<long long>(::recvfrom(s, buf, len, 0, addr, addr_len));
#endif
}

}  // namespace telegram_like::client::net
