#include "net/socket_subsystem.h"

#include <mutex>

namespace telegram_like::client::net {

namespace {

#if defined(_WIN32)
std::mutex& wsa_mutex() {
    static std::mutex m;
    return m;
}

int& wsa_refcount() {
    static int n = 0;
    return n;
}
#endif

}  // namespace

SocketSubsystem::SocketSubsystem() : ok_(true) {
#if defined(_WIN32)
    std::lock_guard lock(wsa_mutex());
    if (wsa_refcount() == 0) {
        WSADATA data {};
        if (::WSAStartup(MAKEWORD(2, 2), &data) != 0) {
            ok_ = false;
            return;
        }
    }
    ++wsa_refcount();
#endif
}

SocketSubsystem::~SocketSubsystem() {
#if defined(_WIN32)
    if (!ok_) {
        return;
    }
    std::lock_guard lock(wsa_mutex());
    if (--wsa_refcount() == 0) {
        ::WSACleanup();
    }
#endif
}

}  // namespace telegram_like::client::net
