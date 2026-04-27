#include "net/socket_error.h"

namespace telegram_like::client::net {

int last_native_error() noexcept {
#if defined(_WIN32)
    return ::WSAGetLastError();
#else
    return errno;
#endif
}

NetErrorCode map_native_error(int err) noexcept {
    if (err == 0) {
        return NetErrorCode::kOk;
    }

#if defined(_WIN32)
    switch (err) {
        case WSAEWOULDBLOCK:   return NetErrorCode::kWouldBlock;
        case WSAETIMEDOUT:     return NetErrorCode::kTimeout;
        case WSAECONNREFUSED:  return NetErrorCode::kConnectionRefused;
        case WSAECONNRESET:    return NetErrorCode::kConnectionReset;
        case WSAEHOSTUNREACH:  return NetErrorCode::kHostUnreachable;
        case WSAENETUNREACH:   return NetErrorCode::kNetworkUnreachable;
        case WSAEADDRINUSE:    return NetErrorCode::kAddressInUse;
        case WSAEADDRNOTAVAIL: return NetErrorCode::kAddressNotAvailable;
        case WSAEINTR:         return NetErrorCode::kInterrupted;
        case WSAENOTCONN:      return NetErrorCode::kNotConnected;
        case WSAESHUTDOWN:     return NetErrorCode::kShutdown;
        case WSAEACCES:        return NetErrorCode::kPermissionDenied;
        case WSAHOST_NOT_FOUND:
        case WSANO_DATA:       return NetErrorCode::kDnsFailure;
        default:               return NetErrorCode::kUnknown;
    }
#else
    switch (err) {
        case EAGAIN:
#if defined(EWOULDBLOCK) && (EWOULDBLOCK != EAGAIN)
        case EWOULDBLOCK:
#endif
                               return NetErrorCode::kWouldBlock;
        case ETIMEDOUT:        return NetErrorCode::kTimeout;
        case ECONNREFUSED:     return NetErrorCode::kConnectionRefused;
        case ECONNRESET:       return NetErrorCode::kConnectionReset;
        case EHOSTUNREACH:     return NetErrorCode::kHostUnreachable;
        case ENETUNREACH:      return NetErrorCode::kNetworkUnreachable;
        case EADDRINUSE:       return NetErrorCode::kAddressInUse;
        case EADDRNOTAVAIL:    return NetErrorCode::kAddressNotAvailable;
        case EINTR:            return NetErrorCode::kInterrupted;
        case ENOTCONN:         return NetErrorCode::kNotConnected;
        case ESHUTDOWN:        return NetErrorCode::kShutdown;
        case EACCES:           return NetErrorCode::kPermissionDenied;
        default:               return NetErrorCode::kUnknown;
    }
#endif
}

std::string describe(NetErrorCode code) {
    switch (code) {
        case NetErrorCode::kOk:                  return "ok";
        case NetErrorCode::kWouldBlock:          return "would_block";
        case NetErrorCode::kTimeout:             return "timeout";
        case NetErrorCode::kConnectionRefused:   return "connection_refused";
        case NetErrorCode::kConnectionReset:     return "connection_reset";
        case NetErrorCode::kHostUnreachable:     return "host_unreachable";
        case NetErrorCode::kNetworkUnreachable:  return "network_unreachable";
        case NetErrorCode::kAddressInUse:        return "address_in_use";
        case NetErrorCode::kAddressNotAvailable: return "address_not_available";
        case NetErrorCode::kInterrupted:         return "interrupted";
        case NetErrorCode::kNotConnected:        return "not_connected";
        case NetErrorCode::kShutdown:            return "shutdown";
        case NetErrorCode::kDnsFailure:          return "dns_failure";
        case NetErrorCode::kPermissionDenied:    return "permission_denied";
        case NetErrorCode::kUnknown:             return "unknown";
    }
    return "unknown";
}

}  // namespace telegram_like::client::net
