"""Audio capture + playback abstraction (M127).

Real capture/playback is platform-specific (CoreAudio / WASAPI / ALSA /
AAudio / OpenSL ES). The Protocol-typed seam here lets us:

- Build call flow validators against SyntheticAudioSource +
  MemoryAudioSink (deterministic, no device).
- Plug in platform-specific implementations later without touching the
  CallSession or RelayPeerSession code paths.
"""
from __future__ import annotations

import math
import struct
from typing import Iterable, Optional, Protocol


class AudioSource(Protocol):
    sample_rate: int
    channels: int
    samples_per_frame: int

    def next_frame(self) -> Optional[bytes]: ...


class AudioSink(Protocol):
    sample_rate: int
    channels: int
    samples_per_frame: int

    def feed(self, pcm_frame: bytes) -> None: ...


class SyntheticAudioSource:
    """Deterministic 16-bit PCM sine-wave source for tests.

    Produces `frame_count` frames of the configured duration; returns None
    once exhausted. The waveform is a pure tone so a downstream decoder
    can sanity-check the bytes without parsing real audio.
    """

    def __init__(
        self,
        *,
        sample_rate: int = 48_000,
        channels: int = 1,
        samples_per_frame: int = 960,
        frame_count: int = 50,
        tone_hz: int = 440,
    ) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.samples_per_frame = samples_per_frame
        self._remaining = frame_count
        self._tone_hz = tone_hz
        self._frame_index = 0

    def next_frame(self) -> Optional[bytes]:
        if self._remaining <= 0:
            return None
        self._remaining -= 1
        body: list[int] = []
        base = self._frame_index * self.samples_per_frame
        for i in range(self.samples_per_frame):
            t = (base + i) / float(self.sample_rate)
            sample = int(0.4 * 32767 * math.sin(2.0 * math.pi * self._tone_hz * t))
            for _ in range(self.channels):
                body.append(sample)
        self._frame_index += 1
        return struct.pack(f">{len(body)}h", *body)


class MemoryAudioSink:
    """Captures every fed frame in-memory; useful for assertions in tests."""

    def __init__(self, *, sample_rate: int = 48_000, channels: int = 1,
                 samples_per_frame: int = 960) -> None:
        self.sample_rate = sample_rate
        self.channels = channels
        self.samples_per_frame = samples_per_frame
        self.frames: list[bytes] = []

    def feed(self, pcm_frame: bytes) -> None:
        self.frames.append(pcm_frame)


def drain(source: AudioSource) -> Iterable[bytes]:
    while True:
        frame = source.next_frame()
        if frame is None:
            return
        yield frame
