#include "net/tcp_line_client.h"

#include <algorithm>
#include <array>
#include <chrono>
#include <cstring>
#include <iostream>

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
    if (!connect_socket(host, port)) {
        return false;
    }
    start_reader();
    return true;
}

bool TcpLineClient::connect_tls(const std::string& host,
                                unsigned short port,
                                TlsVerifyMode verify_mode,
                                const std::string& server_name) {
    disconnect();
    if (!subsystem_.ok()) {
        last_error_.store(NetErrorCode::kUnknown);
        return false;
    }
#if defined(_WIN32)
    if (!connect_socket(host, port)) {
        return false;
    }
    const std::string sni = server_name.empty() ? host : server_name;
    if (!tls_handshake(sni, verify_mode)) {
        socket_.reset();
        tls_cleanup();
        return false;
    }
    start_reader();
    return true;
#else
    (void)host;
    (void)port;
    (void)verify_mode;
    (void)server_name;
    last_error_.store(NetErrorCode::kUnknown);
    return false;
#endif
}

bool TcpLineClient::connect_socket(const std::string& host, unsigned short port) {
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
    last_error_.store(NetErrorCode::kOk);
    return true;
}

void TcpLineClient::start_reader() {
    running_.store(true);
    reader_ = std::thread(&TcpLineClient::reader_loop, this);
}

void TcpLineClient::disconnect() {
    shutdown_reader();
    socket_.reset();
#if defined(_WIN32)
    tls_cleanup();
#endif
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
        const long long sent = transport_send(framed.data() + sent_total,
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
        const long long received = transport_recv(chunk.data(), chunk.size());
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

long long TcpLineClient::transport_send(const void* data, std::size_t size) {
#if defined(_WIN32)
    if (tls_enabled_) {
        return tls_send(data, size);
    }
#endif
    return native_send(socket_.get(), data, size);
}

long long TcpLineClient::transport_recv(void* data, std::size_t size) {
#if defined(_WIN32)
    if (tls_enabled_) {
        return tls_recv(data, size);
    }
#endif
    return native_recv(socket_.get(), data, size);
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

#if defined(_WIN32)

bool TcpLineClient::send_all_native(const void* data, std::size_t size) {
    const char* cursor = static_cast<const char*>(data);
    std::size_t sent_total = 0;
    while (sent_total < size) {
        const long long sent = native_send(socket_.get(), cursor + sent_total, size - sent_total);
        if (sent == kSocketError || sent <= 0) {
            last_error_.store(last_error());
            return false;
        }
        sent_total += static_cast<std::size_t>(sent);
    }
    return true;
}

bool TcpLineClient::tls_handshake(const std::string& server_name, TlsVerifyMode verify_mode) {
    // Some Windows hosts return SEC_E_NO_CREDENTIALS when pAuthData is null because
    // no default outbound Schannel credentials exist for the calling user. Build an
    // explicit anonymous-client SCHANNEL_CRED so the call succeeds without relying
    // on machine-wide defaults.
    SCHANNEL_CRED cred_data {};
    cred_data.dwVersion = SCHANNEL_CRED_VERSION;
    cred_data.grbitEnabledProtocols = 0;
    cred_data.dwFlags = SCH_CRED_NO_DEFAULT_CREDS | SCH_USE_STRONG_CRYPTO;
    if (verify_mode == TlsVerifyMode::InsecureSkipVerify) {
        cred_data.dwFlags |= SCH_CRED_MANUAL_CRED_VALIDATION;
    }

    SECURITY_STATUS status = ::AcquireCredentialsHandleW(
        nullptr,
        const_cast<wchar_t*>(UNISP_NAME_W),
        SECPKG_CRED_OUTBOUND,
        nullptr,
        &cred_data,
        nullptr,
        nullptr,
        &tls_credentials_,
        nullptr);
    if (status != SEC_E_OK) {
        std::cerr << "tls: AcquireCredentialsHandle failed status=0x"
                  << std::hex << status << std::dec << "\n";
        last_error_.store(NetErrorCode::kUnknown);
        return false;
    }
    tls_have_credentials_ = true;

    DWORD context_flags = ISC_REQ_SEQUENCE_DETECT
        | ISC_REQ_REPLAY_DETECT
        | ISC_REQ_CONFIDENTIALITY
        | ISC_REQ_ALLOCATE_MEMORY
        | ISC_REQ_STREAM;
    if (verify_mode == TlsVerifyMode::InsecureSkipVerify) {
        context_flags |= ISC_REQ_MANUAL_CRED_VALIDATION;
    }
    DWORD context_attributes = 0;
    SecBuffer out_buffer {};
    out_buffer.BufferType = SECBUFFER_TOKEN;
    SecBufferDesc out_desc {};
    out_desc.ulVersion = SECBUFFER_VERSION;
    out_desc.cBuffers = 1;
    out_desc.pBuffers = &out_buffer;

    status = ::InitializeSecurityContextA(
        &tls_credentials_,
        nullptr,
        const_cast<char*>(server_name.c_str()),
        context_flags,
        0,
        SECURITY_NATIVE_DREP,
        nullptr,
        0,
        &tls_context_,
        &out_desc,
        &context_attributes,
        nullptr);
    if (status != SEC_I_CONTINUE_NEEDED || out_buffer.cbBuffer == 0 || out_buffer.pvBuffer == nullptr) {
        if (out_buffer.pvBuffer) ::FreeContextBuffer(out_buffer.pvBuffer);
        std::cerr << "tls: initial InitializeSecurityContext failed status=0x"
                  << std::hex << status << std::dec << "\n";
        last_error_.store(NetErrorCode::kUnknown);
        return false;
    }
    tls_have_context_ = true;
    if (!send_all_native(out_buffer.pvBuffer, out_buffer.cbBuffer)) {
        ::FreeContextBuffer(out_buffer.pvBuffer);
        return false;
    }
    ::FreeContextBuffer(out_buffer.pvBuffer);

    std::vector<char> input;
    input.reserve(8192);
    std::array<char, 4096> read_buffer {};
    while (status == SEC_I_CONTINUE_NEEDED || status == SEC_E_INCOMPLETE_MESSAGE) {
        if (status == SEC_E_INCOMPLETE_MESSAGE || input.empty()) {
            const long long received = native_recv(socket_.get(), read_buffer.data(), read_buffer.size());
            if (received == kSocketError || received <= 0) {
                last_error_.store(last_error());
                return false;
            }
            input.insert(input.end(), read_buffer.data(), read_buffer.data() + received);
        }

        SecBuffer in_buffers[2] {};
        in_buffers[0].BufferType = SECBUFFER_TOKEN;
        in_buffers[0].pvBuffer = input.data();
        in_buffers[0].cbBuffer = static_cast<unsigned long>(input.size());
        in_buffers[1].BufferType = SECBUFFER_EMPTY;
        SecBufferDesc in_desc {};
        in_desc.ulVersion = SECBUFFER_VERSION;
        in_desc.cBuffers = 2;
        in_desc.pBuffers = in_buffers;

        out_buffer = {};
        out_buffer.BufferType = SECBUFFER_TOKEN;
        out_desc.pBuffers = &out_buffer;

        status = ::InitializeSecurityContextA(
            &tls_credentials_,
            &tls_context_,
            const_cast<char*>(server_name.c_str()),
            context_flags,
            0,
            SECURITY_NATIVE_DREP,
            &in_desc,
            0,
            &tls_context_,
            &out_desc,
            &context_attributes,
            nullptr);

        if (out_buffer.cbBuffer > 0 && out_buffer.pvBuffer != nullptr) {
            const bool sent = send_all_native(out_buffer.pvBuffer, out_buffer.cbBuffer);
            ::FreeContextBuffer(out_buffer.pvBuffer);
            if (!sent) return false;
        }
        if (status == SEC_E_INCOMPLETE_MESSAGE) {
            continue;
        }
        if (status != SEC_E_OK && status != SEC_I_CONTINUE_NEEDED) {
            std::cerr << "tls: InitializeSecurityContext failed status=0x"
                      << std::hex << status << std::dec << "\n";
            last_error_.store(NetErrorCode::kUnknown);
            return false;
        }
        if (in_buffers[1].BufferType == SECBUFFER_EXTRA && in_buffers[1].cbBuffer > 0) {
            const auto extra = static_cast<std::size_t>(in_buffers[1].cbBuffer);
            std::vector<char> tail(input.end() - static_cast<std::ptrdiff_t>(extra), input.end());
            input = std::move(tail);
        } else {
            input.clear();
        }
    }

    status = ::QueryContextAttributesA(&tls_context_, SECPKG_ATTR_STREAM_SIZES, &tls_sizes_);
    if (status != SEC_E_OK) {
        std::cerr << "tls: QueryContextAttributes failed status=0x"
                  << std::hex << status << std::dec << "\n";
        last_error_.store(NetErrorCode::kUnknown);
        return false;
    }
    tls_encrypted_in_ = std::move(input);
    tls_enabled_ = true;
    return true;
}

void TcpLineClient::tls_cleanup() noexcept {
    tls_enabled_ = false;
    tls_encrypted_in_.clear();
    tls_plain_in_.clear();
    if (tls_have_context_) {
        ::DeleteSecurityContext(&tls_context_);
        tls_context_ = {};
        tls_have_context_ = false;
    }
    if (tls_have_credentials_) {
        ::FreeCredentialsHandle(&tls_credentials_);
        tls_credentials_ = {};
        tls_have_credentials_ = false;
    }
    tls_sizes_ = {};
}

long long TcpLineClient::tls_send(const void* data, std::size_t size) {
    const char* cursor = static_cast<const char*>(data);
    std::size_t sent_total = 0;
    while (sent_total < size) {
        const auto chunk_size = (std::min)(size - sent_total,
            static_cast<std::size_t>(tls_sizes_.cbMaximumMessage));
        std::vector<char> record(tls_sizes_.cbHeader + chunk_size + tls_sizes_.cbTrailer);
        std::memcpy(record.data() + tls_sizes_.cbHeader, cursor + sent_total, chunk_size);

        SecBuffer buffers[4] {};
        buffers[0].BufferType = SECBUFFER_STREAM_HEADER;
        buffers[0].pvBuffer = record.data();
        buffers[0].cbBuffer = tls_sizes_.cbHeader;
        buffers[1].BufferType = SECBUFFER_DATA;
        buffers[1].pvBuffer = record.data() + tls_sizes_.cbHeader;
        buffers[1].cbBuffer = static_cast<unsigned long>(chunk_size);
        buffers[2].BufferType = SECBUFFER_STREAM_TRAILER;
        buffers[2].pvBuffer = record.data() + tls_sizes_.cbHeader + chunk_size;
        buffers[2].cbBuffer = tls_sizes_.cbTrailer;
        buffers[3].BufferType = SECBUFFER_EMPTY;
        SecBufferDesc desc {};
        desc.ulVersion = SECBUFFER_VERSION;
        desc.cBuffers = 4;
        desc.pBuffers = buffers;

        const SECURITY_STATUS status = ::EncryptMessage(&tls_context_, 0, &desc, 0);
        if (status != SEC_E_OK) {
            last_error_.store(NetErrorCode::kUnknown);
            return kSocketError;
        }
        const std::size_t encrypted_size = buffers[0].cbBuffer + buffers[1].cbBuffer + buffers[2].cbBuffer;
        if (!send_all_native(record.data(), encrypted_size)) {
            return kSocketError;
        }
        sent_total += chunk_size;
    }
    return static_cast<long long>(size);
}

long long TcpLineClient::tls_recv(void* data, std::size_t size) {
    while (tls_plain_in_.empty()) {
        if (tls_encrypted_in_.empty()) {
            std::array<char, 4096> read_buffer {};
            const long long received = native_recv(socket_.get(), read_buffer.data(), read_buffer.size());
            if (received == kSocketError || received <= 0) {
                last_error_.store(last_error());
                return received;
            }
            tls_encrypted_in_.insert(tls_encrypted_in_.end(),
                                     read_buffer.data(),
                                     read_buffer.data() + received);
        }

        SecBuffer buffers[4] {};
        buffers[0].BufferType = SECBUFFER_DATA;
        buffers[0].pvBuffer = tls_encrypted_in_.data();
        buffers[0].cbBuffer = static_cast<unsigned long>(tls_encrypted_in_.size());
        buffers[1].BufferType = SECBUFFER_EMPTY;
        buffers[2].BufferType = SECBUFFER_EMPTY;
        buffers[3].BufferType = SECBUFFER_EMPTY;
        SecBufferDesc desc {};
        desc.ulVersion = SECBUFFER_VERSION;
        desc.cBuffers = 4;
        desc.pBuffers = buffers;

        const SECURITY_STATUS status = ::DecryptMessage(&tls_context_, &desc, 0, nullptr);
        if (status == SEC_E_INCOMPLETE_MESSAGE) {
            std::array<char, 4096> read_buffer {};
            const long long received = native_recv(socket_.get(), read_buffer.data(), read_buffer.size());
            if (received == kSocketError || received <= 0) {
                last_error_.store(last_error());
                return received;
            }
            tls_encrypted_in_.insert(tls_encrypted_in_.end(),
                                     read_buffer.data(),
                                     read_buffer.data() + received);
            continue;
        }
        if (status == SEC_I_CONTEXT_EXPIRED) {
            return 0;
        }
        if (status != SEC_E_OK) {
            last_error_.store(NetErrorCode::kUnknown);
            return kSocketError;
        }

        for (const auto& buffer : buffers) {
            if (buffer.BufferType == SECBUFFER_DATA && buffer.cbBuffer > 0 && buffer.pvBuffer != nullptr) {
                const char* plain = static_cast<const char*>(buffer.pvBuffer);
                tls_plain_in_.assign(plain, plain + buffer.cbBuffer);
            }
        }

        std::vector<char> extra;
        for (const auto& buffer : buffers) {
            if (buffer.BufferType == SECBUFFER_EXTRA && buffer.cbBuffer > 0 && buffer.pvBuffer != nullptr) {
                const char* tail = static_cast<const char*>(buffer.pvBuffer);
                extra.assign(tail, tail + buffer.cbBuffer);
            }
        }
        tls_encrypted_in_ = std::move(extra);
    }

    const std::size_t copied = (std::min)(size, tls_plain_in_.size());
    std::memcpy(data, tls_plain_in_.data(), copied);
    tls_plain_in_.erase(tls_plain_in_.begin(),
                        tls_plain_in_.begin() + static_cast<std::ptrdiff_t>(copied));
    return static_cast<long long>(copied);
}

#endif

}  // namespace telegram_like::client::net
