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

namespace telegram_like::client::net {

class TcpLineClient {
public:
    using FramePredicate = std::function<bool(const std::string& json_line)>;

    TcpLineClient();
    ~TcpLineClient();

    TcpLineClient(const TcpLineClient&) = delete;
    TcpLineClient& operator=(const TcpLineClient&) = delete;

    [[nodiscard]] bool connect(const std::string& host, unsigned short port);
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
    void reader_loop();
    void shutdown_reader();

    SocketSubsystem subsystem_;
    Socket socket_;
    std::atomic<bool> running_ {false};
    std::atomic<NetErrorCode> last_error_ {NetErrorCode::kOk};
    std::thread reader_;

    std::mutex inbox_mutex_;
    std::condition_variable inbox_cv_;
    std::deque<std::string> inbox_;

    std::mutex write_mutex_;
};

}  // namespace telegram_like::client::net
