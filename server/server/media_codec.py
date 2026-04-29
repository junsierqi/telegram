"""Voice / video codec abstraction (M127).

The call signaling FSM (M109) and the AEAD relay (M105/M106) only deal in
opaque bytes. This module sits between them and a real codec library so
calls can ship a working transport before we link libopus / libvpx.

Default codec is PassThroughCodec — no encoding, frames travel as raw
PCM bytes. Useful for tests and local-network bring-up where bandwidth
isn't the bottleneck.

OpusCodec is a stub gated on PA-012 (libopus dependency procurement).
The class shape matches what a future opuslib-backed implementation will
expose so callers can wire it in without touching the call path.
"""
from __future__ import annotations

import struct
from typing import Optional, Protocol


# 12-byte header carried inside each AEAD-sealed reliable packet so the
# receiver knows what to feed the decoder. Mirrors the media_plane frame
# header shape but keyed for audio:
#   u8 codec_id | u8 channels | u16 sample_rate / 100 | u16 samples_per_frame
#   | u32 sequence | u16 reserved
_AUDIO_HEADER = ">BBHHIH"
AUDIO_HEADER_SIZE = struct.calcsize(_AUDIO_HEADER)

CODEC_PASSTHROUGH = 1
CODEC_OPUS = 2


class Encoder(Protocol):
    codec_id: int
    sample_rate: int
    channels: int
    samples_per_frame: int

    def encode(self, pcm_frame: bytes) -> bytes: ...


class Decoder(Protocol):
    codec_id: int
    sample_rate: int
    channels: int
    samples_per_frame: int

    def decode(self, encoded_frame: bytes) -> bytes: ...


class PassThroughCodec:
    """Identity codec — encode/decode is a memcpy. Default for tests + LAN."""

    codec_id = CODEC_PASSTHROUGH

    def __init__(self, *, sample_rate: int = 48_000, channels: int = 1,
                 samples_per_frame: int = 960) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.samples_per_frame = samples_per_frame

    def encode(self, pcm_frame: bytes) -> bytes:
        return pcm_frame

    def decode(self, encoded_frame: bytes) -> bytes:
        return encoded_frame


class OpusCodec:
    """Stub for a real Opus encoder/decoder.

    Without PA-012 (libopus or opuslib procured), `encode`/`decode` raise
    PermissionError so callers see exactly what's missing. With
    `dry_run=True` the calls fall back to the PassThroughCodec behaviour
    so call-flow tests can run end-to-end before procurement.
    """

    codec_id = CODEC_OPUS

    def __init__(
        self,
        *,
        sample_rate: int = 48_000,
        channels: int = 1,
        samples_per_frame: int = 960,
        dry_run: bool = True,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.samples_per_frame = samples_per_frame
        self.dry_run = dry_run

    def _check(self, op: str) -> None:
        if not self.dry_run:
            raise PermissionError(
                f"OpusCodec.{op} requires PA-012 (libopus / opuslib procured); "
                "run with dry_run=True for now"
            )

    def encode(self, pcm_frame: bytes) -> bytes:
        self._check("encode")
        # Dry-run path: identity. A real impl would call opuslib.Encoder().encode().
        return pcm_frame

    def decode(self, encoded_frame: bytes) -> bytes:
        self._check("decode")
        return encoded_frame


def build_audio_payload(encoder: Encoder, pcm_frame: bytes, sequence: int) -> bytes:
    """Pack header + encoded body for transmission inside a reliable packet."""
    encoded = encoder.encode(pcm_frame)
    header = struct.pack(
        _AUDIO_HEADER,
        encoder.codec_id,
        encoder.channels,
        max(0, min(0xFFFF, encoder.sample_rate // 100)),
        max(0, min(0xFFFF, encoder.samples_per_frame)),
        sequence & 0xFFFFFFFF,
        0,
    )
    return header + encoded


def parse_audio_payload(payload: bytes) -> Optional[tuple[int, int, int, int, int, bytes]]:
    """Return (codec_id, channels, sample_rate, samples_per_frame, sequence,
    encoded_body) or None on a malformed payload."""
    if len(payload) < AUDIO_HEADER_SIZE:
        return None
    codec_id, channels, rate100, samples, sequence, _reserved = struct.unpack(
        _AUDIO_HEADER, payload[:AUDIO_HEADER_SIZE]
    )
    return (
        int(codec_id), int(channels), int(rate100) * 100, int(samples),
        int(sequence), payload[AUDIO_HEADER_SIZE:],
    )
