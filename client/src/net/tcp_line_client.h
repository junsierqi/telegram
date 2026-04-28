#pragma once

// Async JSON-line TCP client.
//
// One background reader thread drains '\n'-delimited frames from the socket
// into a std::deque<std::string> inbox. Writes are serialized via a mutex so
// unsolicited pushes from the higher layer never interleave with request
// bytes. Higher layers use wait_for(predicate, timeout) to block until a
// matching frame arrives (typical: "correlation_id == X" for RPC responses,
// or "always true" to drain pushes).

#include "net/platform.h"
#include "net/socket_error.h"
#include "net/socket_raii.h"
#include "net/socket_subsystem.h"

#include <atomic>
#include <condition_variable>
#include <deque>
#include <functional>
#include <mutex>
#include <optional>
#include <string>
#include <string_view>
#include <thread>
#include <vector>

#if defined(_WIN32)
#ifndef SECURITY_WIN32
#define SECURITY_WIN32
#endif
#include <security.h>
#include <schannel.h>
#endif

namespace telegram_like::client::net {

class TcpLineClient {
public:
    using FramePredicate = std::function<bool(const std::string& json_line)>;

    enum class TlsVerifyMode {
        SystemDefault,
        InsecureSkipVerify,
    };

    TcpLineClient();
    ~TcpLineClient();

    TcpLineClient(const TcpLineClient&) = delete;
    TcpLineClient& operator=(const TcpLineClient&) = delete;

    [[nodiscard]] bool connect(const std::string& host, unsigned short port);
    [[nodiscard]] bool connect_tls(const std::string& host,
                                   unsigned short port,
                                   TlsVerifyMode verify_mode = TlsVerifyMode::SystemDefault,
                                   const std::string& server_name = {});
    void disconnect();
    [[nodiscard]] bool is_connected() const noexcept;
    [[nodiscard]] NetErrorCode last_error() const noexcept { return last_error_.load(); }

    // Serialize send; appends a '\n'. Returns false if disconnected or errored.
    bool send_line(std::string_view line);

    // Block until a frame satisfying `pred` arrives (or timeout). Removes and
    // returns the matching frame; non-matching frames stay queued in order.
    [[nodiscard]] std::optional<std::string> wait_for(
        const FramePredicate& pred, unsigned timeout_ms);

    // Non-blocking: drain every currently buffered frame.
    [[nodiscard]] std::vector<std::string> drain();

    // Convenience predicate builders.
    [[nodiscard]] static FramePredicate match_correlation_id(std::string id);
    [[nodiscard]] static FramePredicate match_any();

private:
    [[nodiscard]] bool connect_socket(const std::string& host, unsigned short port);
    void start_reader();
    void reader_loop();
    void shutdown_reader();
    [[nodiscard]] long long transport_send(const void* data, std::size_t size);
    [[nodiscard]] long long transport_recv(void* data, std::size_t size);

#if defined(_WIN32)
    [[nodiscard]] bool tls_handshake(const std::string& server_name, TlsVerifyMode verify_mode);
    void tls_cleanup() noexcept;
    [[nodiscard]] long long tls_send(const void* data, std::size_t size);
    [[nodiscard]] long long tls_recv(void* data, std::size_t size);
    [[nodiscard]] bool send_all_native(const void* data, std::size_t size);
#endif

    SocketSubsystem subsystem_;
    Socket socket_;
    std::atomic<bool> running_ {false};
    std::atomic<NetErrorCode> last_error_ {NetErrorCode::kOk};
    std::thread reader_;

    std::mutex inbox_mutex_;
    std::condition_variable inbox_cv_;
    std::deque<std::string> inbox_;

    std::mutex write_mutex_;

#if defined(_WIN32)
    bool tls_enabled_ {false};
    bool tls_have_credentials_ {false};
    bool tls_have_context_ {false};
    CredHandle tls_credentials_ {};
    CtxtHandle tls_context_ {};
    SecPkgContext_StreamSizes tls_sizes_ {};
    std::vector<char> tls_encrypted_in_;
    std::vector<char> tls_plain_in_;
#endif
};

}  // namespace telegram_like::client::net
