#include "net/tcp_line_client.h"

#include <array>
#include <chrono>

namespace telegram_like::client::net {

TcpLineClient::TcpLineClient() = default;

TcpLineClient::~TcpLineClient() {
    disconnect();
}

bool TcpLineClient::connect(const std::string& host, unsigned short port) {
    disconnect();
    if (!subsystem_.ok()) {
        last_error_.store(NetErrorCode::kUnknown);
        return false;
    }

    addrinfo hints {};
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    hints.ai_protocol = IPPROTO_TCP;

    addrinfo* result = nullptr;
    const auto port_text = std::to_string(port);
    if (::getaddrinfo(host.c_str(), port_text.c_str(), &hints, &result) != 0) {
        last_error_.store(NetErrorCode::kDnsFailure);
        return false;
    }

    NativeSocket sock = kInvalidSocket;
    for (addrinfo* current = result; current != nullptr; current = current->ai_next) {
        NativeSocket candidate = ::socket(current->ai_family,
                                          current->ai_socktype,
                                          current->ai_protocol);
        if (!is_valid(candidate)) {
            continue;
        }
        if (::connect(candidate, current->ai_addr,
                      static_cast<socklen_type>(current->ai_addrlen)) == 0) {
            sock = candidate;
            break;
        }
        close_native_socket(candidate);
    }
    ::freeaddrinfo(result);

    if (!is_valid(sock)) {
        last_error_.store(last_error());
        return false;
    }

    socket_.reset(sock);
    running_.store(true);
    last_error_.store(NetErrorCode::kOk);
    reader_ = std::thread(&TcpLineClient::reader_loop, this);
    return true;
}

void TcpLineClient::disconnect() {
    shutdown_reader();
    socket_.reset();
    {
        std::lock_guard lock(inbox_mutex_);
        inbox_.clear();
    }
    inbox_cv_.notify_all();
}

bool TcpLineClient::is_connected() const noexcept {
    return running_.load() && socket_.valid();
}

bool TcpLineClient::send_line(std::string_view line) {
    if (!is_connected()) {
        return false;
    }
    std::string framed;
    framed.reserve(line.size() + 1);
    framed.append(line);
    framed.push_back('\n');

    std::lock_guard lock(write_mutex_);
    std::size_t sent_total = 0;
    while (sent_total < framed.size()) {
        const long long sent = native_send(socket_.get(),
                                           framed.data() + sent_total,
                                           framed.size() - sent_total);
        if (sent == kSocketError || sent <= 0) {
            last_error_.store(last_error());
            running_.store(false);
            return false;
        }
        sent_total += static_cast<std::size_t>(sent);
    }
    return true;
}

std::optional<std::string> TcpLineClient::wait_for(
    const FramePredicate& pred, unsigned timeout_ms) {
    const auto deadline = std::chrono::steady_clock::now() +
                          std::chrono::milliseconds(timeout_ms);
    std::unique_lock lock(inbox_mutex_);
    while (true) {
        for (auto it = inbox_.begin(); it != inbox_.end(); ++it) {
            if (pred(*it)) {
                std::string matched = std::move(*it);
                inbox_.erase(it);
                return matched;
            }
        }
        if (!running_.load()) {
            return std::nullopt;
        }
        if (inbox_cv_.wait_until(lock, deadline) == std::cv_status::timeout) {
            // last pass through the queue after timeout, in case race
            for (auto it = inbox_.begin(); it != inbox_.end(); ++it) {
                if (pred(*it)) {
                    std::string matched = std::move(*it);
                    inbox_.erase(it);
                    return matched;
                }
            }
            return std::nullopt;
        }
    }
}

std::vector<std::string> TcpLineClient::drain() {
    std::vector<std::string> out;
    std::lock_guard lock(inbox_mutex_);
    while (!inbox_.empty()) {
        out.push_back(std::move(inbox_.front()));
        inbox_.pop_front();
    }
    return out;
}

TcpLineClient::FramePredicate TcpLineClient::match_correlation_id(std::string id) {
    return [id = std::move(id)](const std::string& line) {
        // naive JSON scan — cheap and good enough for the server's envelope format
        const std::string needle = "\"correlation_id\"";
        const auto pos = line.find(needle);
        if (pos == std::string::npos) return false;
        const auto colon = line.find(':', pos + needle.size());
        if (colon == std::string::npos) return false;
        const auto first_quote = line.find('"', colon);
        if (first_quote == std::string::npos) return false;
        const auto second_quote = line.find('"', first_quote + 1);
        if (second_quote == std::string::npos) return false;
        return line.compare(first_quote + 1, second_quote - first_quote - 1, id) == 0;
    };
}

TcpLineClient::FramePredicate TcpLineClient::match_any() {
    return [](const std::string&) { return true; };
}

void TcpLineClient::reader_loop() {
    std::string buffer;
    std::array<char, 2048> chunk {};
    while (running_.load() && socket_.valid()) {
        const long long received = native_recv(socket_.get(), chunk.data(), chunk.size());
        if (received == kSocketError || received <= 0) {
            last_error_.store(last_error());
            running_.store(false);
            break;
        }
        buffer.append(chunk.data(), static_cast<std::size_t>(received));
        std::size_t newline;
        while ((newline = buffer.find('\n')) != std::string::npos) {
            std::string line = buffer.substr(0, newline);
            buffer.erase(0, newline + 1);
            if (line.empty()) continue;
            {
                std::lock_guard lock(inbox_mutex_);
                inbox_.push_back(std::move(line));
            }
            inbox_cv_.notify_all();
        }
    }
    inbox_cv_.notify_all();
}

void TcpLineClient::shutdown_reader() {
    if (!running_.exchange(false)) {
        return;
    }
    // Shut down the socket to unblock recv() on the reader thread.
#if defined(_WIN32)
    if (socket_.valid()) {
        ::shutdown(socket_.get(), SD_BOTH);
    }
#else
    if (socket_.valid()) {
        ::shutdown(socket_.get(), SHUT_RDWR);
    }
#endif
    inbox_cv_.notify_all();
    if (reader_.joinable()) {
        reader_.join();
    }
}

}  // namespace telegram_like::client::net
