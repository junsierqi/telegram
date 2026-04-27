"""Pluggable frame sources for the UDP media plane.

A "screen source" supplies the pixel bytes (and their dimensions / codec) that
get packed into frame_chunk payloads. The first concrete implementation is
StaticImageScreenSource with a deterministic RGB test pattern — no filesystem
dependencies, byte-exact assertions available.

Real screen capture (OS-level framebuffer grab) will be a separate source type
plugging into the same interface.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .media_plane import CODEC_RAW, build_frame_payload


class ScreenSource(Protocol):
    """Source of frame bodies for the media plane.

    `next_frame(seq, cookie)` returns the FULL frame_chunk payload (header +
    body), so sources can embed per-frame metadata in the header (timestamp).
    """

    @property
    def width(self) -> int: ...

    @property
    def height(self) -> int: ...

    @property
    def codec(self) -> int: ...

    def next_frame(self, seq: int, cookie: bytes) -> bytes: ...


def _gradient_pixels(width: int, height: int) -> bytes:
    """Deterministic RGB gradient. Small enough to fit in one UDP datagram."""
    out = bytearray(width * height * 3)
    idx = 0
    for y in range(height):
        for x in range(width):
            out[idx] = (x * 255) // max(width - 1, 1)
            out[idx + 1] = (y * 255) // max(height - 1, 1)
            out[idx + 2] = ((x + y) * 255) // max(width + height - 2, 1)
            idx += 3
    return bytes(out)


def _solid_pixels(width: int, height: int, rgb: tuple[int, int, int]) -> bytes:
    return bytes(rgb) * (width * height)


_PATTERN_BUILDERS = {
    "gradient": lambda w, h: _gradient_pixels(w, h),
    "black": lambda w, h: _solid_pixels(w, h, (0, 0, 0)),
    "white": lambda w, h: _solid_pixels(w, h, (255, 255, 255)),
    "red": lambda w, h: _solid_pixels(w, h, (255, 0, 0)),
}


def build_test_pattern(width: int, height: int, pattern: str = "gradient") -> bytes:
    try:
        builder = _PATTERN_BUILDERS[pattern]
    except KeyError as exc:
        raise ValueError(
            f"unknown pattern {pattern!r}; known: {sorted(_PATTERN_BUILDERS)}"
        ) from exc
    return builder(width, height)


@dataclass(slots=True)
class StaticImageScreenSource:
    """Static pixel buffer streamed at a fixed frame cadence."""

    width: int
    height: int
    codec: int
    pixels: bytes
    timestamp_step_ms: int = 33  # ~30 fps

    def next_frame(self, seq: int, cookie: bytes) -> bytes:
        body = self.pixels + cookie  # cookie trails the pixel buffer for test pinning
        return build_frame_payload(
            width=self.width,
            height=self.height,
            timestamp_ms=seq * self.timestamp_step_ms,
            codec=self.codec,
            body=body,
        )


def make_test_pattern_source(
    width: int = 24,
    height: int = 16,
    pattern: str = "gradient",
    codec: int = CODEC_RAW,
) -> StaticImageScreenSource:
    return StaticImageScreenSource(
        width=width,
        height=height,
        codec=codec,
        pixels=build_test_pattern(width, height, pattern),
    )
