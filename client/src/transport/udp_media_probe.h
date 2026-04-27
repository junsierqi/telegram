#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace telegram_like::client::transport {

// Matches server/server/media_plane.py framing:
//   4-byte big-endian length of session_id | session_id bytes | payload bytes
// Response format:
//   "ack:" | session_id | ":" | payload
struct UdpProbeResult {
    std::string response_text;
    std::vector<std::uint8_t> response_bytes;
    bool acked {false};
};

[[nodiscard]] std::optional<UdpProbeResult> send_udp_probe(
    const std::string& host,
    unsigned short port,
    const std::string& session_id,
    const std::string& payload,
    unsigned timeout_ms = 2000);

}  // namespace telegram_like::client::transport
