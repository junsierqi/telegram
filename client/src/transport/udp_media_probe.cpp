#include "transport/udp_media_probe.h"

#include "net/platform.h"
#include "net/socket_raii.h"
#include "net/socket_subsystem.h"

#include <array>
#include <cstring>

namespace telegram_like::client::transport {

namespace {

constexpr std::size_t kMaxPacketSize = 1500;
constexpr std::string_view kAckPrefix = "ack:";
constexpr std::string_view kAckSep = ":";

std::vector<std::uint8_t> frame_probe(const std::string& session_id, const std::string& payload) {
    const auto sid_len = static_cast<std::uint32_t>(session_id.size());
    std::vector<std::uint8_t> buffer;
    buffer.reserve(4 + session_id.size() + payload.size());
    buffer.push_back(static_cast<std::uint8_t>((sid_len >> 24) & 0xFF));
    buffer.push_back(static_cast<std::uint8_t>((sid_len >> 16) & 0xFF));
    buffer.push_back(static_cast<std::uint8_t>((sid_len >> 8) & 0xFF));
    buffer.push_back(static_cast<std::uint8_t>(sid_len & 0xFF));
    buffer.insert(buffer.end(), session_id.begin(), session_id.end());
    buffer.insert(buffer.end(), payload.begin(), payload.end());
    return buffer;
}

bool check_ack(const std::vector<std::uint8_t>& bytes, const std::string& session_id) {
    const std::string text(bytes.begin(), bytes.end());
    const std::string expected_prefix = std::string(kAckPrefix) + session_id + std::string(kAckSep);
    return text.rfind(expected_prefix, 0) == 0;
}

}  // namespace

std::optional<UdpProbeResult> send_udp_probe(
    const std::string& host,
    const unsigned short port,
    const std::string& session_id,
    const std::string& payload,
    const unsigned timeout_ms) {
    net::SocketSubsystem subsystem;
    if (!subsystem.ok()) {
        return std::nullopt;
    }

    net::Socket sock(::socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP));
    if (!sock.valid()) {
        return std::nullopt;
    }

    sockaddr_in addr {};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    if (::inet_pton(AF_INET, host.c_str(), &addr.sin_addr) != 1) {
        return std::nullopt;
    }

    const auto frame = frame_probe(session_id, payload);
    const long long sent = net::native_sendto(sock.get(),
                                              frame.data(),
                                              frame.size(),
                                              reinterpret_cast<sockaddr*>(&addr),
                                              static_cast<net::socklen_type>(sizeof(addr)));
    if (sent == net::kSocketError) {
        return std::nullopt;
    }

    net::set_recv_timeout_ms(sock.get(), timeout_ms);

    std::array<char, kMaxPacketSize> buffer {};
    sockaddr_in from {};
    net::socklen_type from_len = static_cast<net::socklen_type>(sizeof(from));
    const long long received = net::native_recvfrom(sock.get(),
                                                    buffer.data(),
                                                    buffer.size(),
                                                    reinterpret_cast<sockaddr*>(&from),
                                                    &from_len);
    if (received == net::kSocketError || received <= 0) {
        return std::nullopt;
    }

    UdpProbeResult result;
    result.response_bytes.assign(buffer.begin(), buffer.begin() + received);
    result.response_text.assign(buffer.data(), static_cast<std::size_t>(received));
    result.acked = check_ack(result.response_bytes, session_id);
    return result;
}

}  // namespace telegram_like::client::transport
