"""Pixel-diff validator for desktop GUI smoke screenshots.

The script intentionally uses only the Python standard library so it can run
in the same environments as the existing validators. It compares PNG files
from a current screenshot directory against a baseline directory and fails
when dimensions differ or when pixel differences exceed configured thresholds.

Default paths:

  current:  artifacts/desktop-gui-smoke
  baseline: artifacts/desktop-reference-baseline

Use `--update-baseline` after an intentional visual change to replace the
baseline with the current screenshots.
"""
from __future__ import annotations

import argparse
import shutil
import struct
import sys
import zlib
from dataclasses import dataclass
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
DEFAULT_CURRENT = REPO / "artifacts" / "desktop-gui-smoke"
DEFAULT_BASELINE = REPO / "artifacts" / "desktop-reference-baseline"
DEFAULT_FILES = ("main-window.png", "account-drawer.png", "settings-modal.png")


@dataclass(frozen=True)
class PngImage:
    width: int
    height: int
    rgba: bytes


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa = abs(p - a)
    pb = abs(p - b)
    pc = abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def read_png(path: Path) -> PngImage:
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise ValueError(f"{path} is not a PNG")

    pos = 8
    width = height = bit_depth = color_type = None
    idat = bytearray()
    while pos < len(data):
        if pos + 8 > len(data):
            raise ValueError(f"{path} has truncated chunk header")
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        chunk_type = data[pos + 4:pos + 8]
        chunk_data = data[pos + 8:pos + 8 + length]
        pos += 12 + length
        if chunk_type == b"IHDR":
            width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
                ">IIBBBBB", chunk_data
            )
            if bit_depth != 8 or compression != 0 or filter_method != 0 or interlace != 0:
                raise ValueError(f"{path} uses unsupported PNG encoding")
            if color_type not in (2, 6):
                raise ValueError(f"{path} uses unsupported PNG color type {color_type}")
        elif chunk_type == b"IDAT":
            idat.extend(chunk_data)
        elif chunk_type == b"IEND":
            break

    if width is None or height is None or bit_depth is None or color_type is None:
        raise ValueError(f"{path} missing IHDR")

    channels = 3 if color_type == 2 else 4
    stride = width * channels
    raw = zlib.decompress(bytes(idat))
    out = bytearray()
    prev = bytearray(stride)
    offset = 0
    for _ in range(height):
        filter_type = raw[offset]
        offset += 1
        scan = bytearray(raw[offset:offset + stride])
        offset += stride
        for i in range(stride):
            left = scan[i - channels] if i >= channels else 0
            up = prev[i]
            up_left = prev[i - channels] if i >= channels else 0
            if filter_type == 0:
                value = scan[i]
            elif filter_type == 1:
                value = (scan[i] + left) & 0xFF
            elif filter_type == 2:
                value = (scan[i] + up) & 0xFF
            elif filter_type == 3:
                value = (scan[i] + ((left + up) >> 1)) & 0xFF
            elif filter_type == 4:
                value = (scan[i] + _paeth(left, up, up_left)) & 0xFF
            else:
                raise ValueError(f"{filter_type} is an unsupported PNG filter in {path}")
            scan[i] = value
        prev = scan
        if channels == 4:
            out.extend(scan)
        else:
            for i in range(0, len(scan), 3):
                out.extend((scan[i], scan[i + 1], scan[i + 2], 255))

    return PngImage(width=width, height=height, rgba=bytes(out))


def diff_images(a: PngImage, b: PngImage) -> tuple[int, float, int]:
    if a.width != b.width or a.height != b.height:
        raise ValueError(f"dimension mismatch {a.width}x{a.height} vs {b.width}x{b.height}")
    pixels = a.width * a.height
    changed = 0
    total_delta = 0
    max_delta = 0
    for i in range(0, len(a.rgba), 4):
        # Alpha is included in max/avg so transparency regressions are visible.
        delta = (
            abs(a.rgba[i] - b.rgba[i])
            + abs(a.rgba[i + 1] - b.rgba[i + 1])
            + abs(a.rgba[i + 2] - b.rgba[i + 2])
            + abs(a.rgba[i + 3] - b.rgba[i + 3])
        )
        if delta:
            changed += 1
            total_delta += delta
            max_delta = max(max_delta, delta)
    changed_pct = (changed / pixels) * 100 if pixels else 0.0
    avg_delta = total_delta / pixels if pixels else 0.0
    return changed, changed_pct, int(round(avg_delta)), max_delta


def update_baseline(current: Path, baseline: Path, files: tuple[str, ...]) -> int:
    baseline.mkdir(parents=True, exist_ok=True)
    for name in files:
        src = current / name
        if not src.exists():
            print(f"[FAIL] current screenshot missing: {src}")
            return 1
        shutil.copy2(src, baseline / name)
        print(f"[ok ] baseline updated: {baseline / name}")
    return 0


def validate(current: Path, baseline: Path, files: tuple[str, ...],
             max_changed_pct: float, max_avg_delta: float, max_channel_delta: int) -> int:
    missing_inputs = [
        path
        for directory in (current, baseline)
        for path in (directory / name for name in files)
        if not path.exists()
    ]
    if missing_inputs:
        print("[skip] desktop image diff artifacts are not available")
        for path in missing_inputs:
            print(f"[skip] missing: {path}")
        return 0

    fail = 0
    for name in files:
        cur = current / name
        base = baseline / name
        try:
            cur_img = read_png(cur)
            base_img = read_png(base)
            changed, changed_pct, avg_delta, max_delta = diff_images(cur_img, base_img)
        except Exception as exc:
            print(f"[FAIL] {name}: {exc}")
            fail += 1
            continue
        print(
            f"[diff] {name}: size={cur_img.width}x{cur_img.height} "
            f"changed={changed_pct:.4f}% avg_delta={avg_delta} max_delta={max_delta}"
        )
        if changed_pct > max_changed_pct or avg_delta > max_avg_delta or max_delta > max_channel_delta:
            print(
                f"[FAIL] {name}: exceeds thresholds "
                f"changed<={max_changed_pct}% avg<={max_avg_delta} max<={max_channel_delta}"
            )
            fail += 1
        else:
            print(f"[ok ] {name}: within pixel thresholds")
    if fail:
        print(f"Result: FAIL ({fail} image issues)")
        return 1
    print("Result: PASS")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--current", type=Path, default=DEFAULT_CURRENT)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--update-baseline", action="store_true")
    parser.add_argument("--max-changed-pct", type=float, default=0.02)
    parser.add_argument("--max-avg-delta", type=float, default=0.5)
    parser.add_argument("--max-channel-delta", type=int, default=16)
    args = parser.parse_args()

    files = tuple(DEFAULT_FILES)
    if args.update_baseline:
        return update_baseline(args.current, args.baseline, files)
    return validate(
        args.current,
        args.baseline,
        files,
        args.max_changed_pct,
        args.max_avg_delta,
        args.max_channel_delta,
    )


if __name__ == "__main__":
    raise SystemExit(main())
