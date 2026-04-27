#include "transport/udp_frame_stream.h"

#include "net/platform.h"
#include "net/socket_raii.h"
#include "net/socket_subsystem.h"

#include <array>
#include <cstring>

namespace telegram_like::client::transport {

namespace {

constexpr std::size_t kMaxPacketSize = 1500;
constexpr std::uint8_t kFrameChunkKind = 'F';
constexpr std::size_t kFrameHeaderSize = 1 + 4 + 4;      // kind | seq | len
constexpr std::size_t kPayloadHeaderSize = 2 + 2 + 4 + 1 + 3;  // w|h|ts|codec|rsv

std::uint32_t read_u32_be(const std::uint8_t* p) {
    return (static_cast<std::uint32_t>(p[0]) << 24) |
           (static_cast<std::uint32_t>(p[1]) << 16) |
           (static_cast<std::uint32_t>(p[2]) << 8) |
           static_cast<std::uint32_t>(p[3]);
}

std::uint16_t read_u16_be(const std::uint8_t* p) {
    return static_cast<std::uint16_t>((p[0] << 8) | p[1]);
}

void write_u32_be(std::vector<std::uint8_t>& buf, std::uint32_t value) {
    buf.push_back(static_cast<std::uint8_t>((value >> 24) & 0xFF));
    buf.push_back(static_cast<std::uint8_t>((value >> 16) & 0xFF));
    buf.push_back(static_cast<std::uint8_t>((value >> 8) & 0xFF));
    buf.push_back(static_cast<std::uint8_t>(value & 0xFF));
}

std::vector<std::uint8_t> build_subscribe_envelope(const std::string& session_id,
                                                   std::uint32_t frame_count,
                                                   const std::string& cookie) {
    std::vector<std::uint8_t> out;
    out.reserve(4 + session_id.size() + 16 + cookie.size());
    write_u32_be(out, static_cast<std::uint32_t>(session_id.size()));
    out.insert(out.end(), session_id.begin(), session_id.end());

    // Body = "SUB:<count>:<cookie>"
    const std::string count_str = std::to_string(frame_count);
    const std::string prefix = "SUB:";
    out.insert(out.end(), prefix.begin(), prefix.end());
    out.insert(out.end(), count_str.begin(), count_str.end());
    out.push_back(':');
    out.insert(out.end(), cookie.begin(), cookie.end());
    return out;
}

// Peel the sid_len|sid envelope; return a pointer and size of the body, or
// std::nullopt on malformed input.
struct EnvelopeView {
    const std::uint8_t* body {nullptr};
    std::size_t body_size {0};
};

std::optional<EnvelopeView> unwrap_envelope(const std::uint8_t* data, std::size_t size) {
    if (size < 4) return std::nullopt;
    const std::uint32_t sid_len = read_u32_be(data);
    if (4 + sid_len > size) return std::nullopt;
    return EnvelopeView {data + 4 + sid_len, size - 4 - sid_len};
}

std::optional<FrameChunk> parse_frame_chunk(const std::uint8_t* body, std::size_t size) {
    if (size < kFrameHeaderSize) return std::nullopt;
    if (body[0] != kFrameChunkKind) return std::nullopt;
    const std::uint32_t seq = read_u32_be(body + 1);
    const std::uint32_t payload_len = read_u32_be(body + 5);
    if (kFrameHeaderSize + payload_len > size) return std::nullopt;
    if (payload_len < kPayloadHeaderSize) return std::nullopt;

    const std::uint8_t* payload = body + kFrameHeaderSize;
    FrameChunk chunk;
    chunk.seq = seq;
    chunk.width = read_u16_be(payload);
    chunk.height = read_u16_be(payload + 2);
    chunk.timestamp_ms = read_u32_be(payload + 4);
    chunk.codec = payload[8];
    chunk.body.assign(payload + kPayloadHeaderSize, payload + payload_len);
    return chunk;
}

}  // namespace

FrameStreamResult subscribe_and_collect(const std::string& host,
                                        const unsigned short port,
                                        const std::string& session_id,
                                        const std::uint32_t frame_count,
                                        const std::string& cookie,
                                        const unsigned timeout_ms) {
    FrameStreamResult out;
    if (frame_count == 0) {
        return out;
    }

    net::SocketSubsystem subsystem;
    if (!subsystem.ok()) {
        out.error = "wsa_startup_failed";
        return out;
    }

    net::Socket sock(::socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP));
    if (!sock.valid()) {
        out.error = "socket_failed";
        return out;
    }

    sockaddr_in addr {};
    addr.sin_family = AF_INET;
    addr.sin_port = htons(port);
    if (::inet_pton(AF_INET, host.c_str(), &addr.sin_addr) != 1) {
        out.error = "inet_pton_failed";
        return out;
    }

    const auto request = build_subscribe_envelope(session_id, frame_count, cookie);
    const long long sent = net::native_sendto(sock.get(),
                                              request.data(),
                                              request.size(),
                                              reinterpret_cast<sockaddr*>(&addr),
                                              static_cast<net::socklen_type>(sizeof(addr)));
    if (sent == net::kSocketError) {
        out.error = "sendto_failed";
        return out;
    }

    net::set_recv_timeout_ms(sock.get(), timeout_ms);

    std::array<std::uint8_t, kMaxPacketSize> buffer {};
    while (out.frames.size() < frame_count) {
        sockaddr_in from {};
        net::socklen_type from_len = static_cast<net::socklen_type>(sizeof(from));
        const long long received = net::native_recvfrom(sock.get(),
                                                        buffer.data(),
                                                        buffer.size(),
                                                        reinterpret_cast<sockaddr*>(&from),
                                                        &from_len);
        if (received == net::kSocketError || received <= 0) {
            out.error = "recv_timeout_or_error";
            return out;
        }

        const auto envelope = unwrap_envelope(buffer.data(),
                                              static_cast<std::size_t>(received));
        if (!envelope.has_value()) {
            out.error = "malformed_envelope";
            return out;
        }
        const auto chunk = parse_frame_chunk(envelope->body, envelope->body_size);
        if (!chunk.has_value()) {
            out.error = "malformed_frame_chunk";
            return out;
        }
        out.frames.push_back(*chunk);
    }

    return out;
}

}  // namespace telegram_like::client::transport
