#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace telegram_like::client::transport {

struct FrameChunk {
    std::uint32_t seq {0};
    std::uint16_t width {0};
    std::uint16_t height {0};
    std::uint32_t timestamp_ms {0};
    std::uint8_t codec {0};
    std::vector<std::uint8_t> body;
};

struct FrameStreamResult {
    std::vector<FrameChunk> frames;
    std::string error;  // empty when successful
};

// Send a subscribe probe and collect `frame_count` structured frame_chunks.
// Wire format matches server/server/media_plane.py:
//   envelope(sid_len|sid|body), body = "SUB:<count>:<cookie>"
//   response envelope(sid_len|sid|frame_body),
//     frame_body = 'F' | u32 seq | u32 payload_len | payload
//     payload   = u16 width | u16 height | u32 ts_ms | u8 codec | 3 reserved | body
[[nodiscard]] FrameStreamResult subscribe_and_collect(
    const std::string& host,
    unsigned short port,
    const std::string& session_id,
    std::uint32_t frame_count,
    const std::string& cookie = "",
    unsigned timeout_ms = 2000);

}  // namespace telegram_like::client::transport
