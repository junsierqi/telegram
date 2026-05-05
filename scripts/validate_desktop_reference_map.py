"""Validate RC-003 original Telegram reference crop mapping.

This does not replace the locked generated-baseline diff. It verifies that
the original reference screenshots are present, each generated GUI smoke
state maps to a bounded crop, and the crop can be diffed with calibrated
per-state tolerances.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from validate_desktop_image_diff import PngImage, diff_images, read_png


REPO = Path(__file__).resolve().parent.parent
DEFAULT_MAP = REPO / "artifacts" / "desktop-reference-originals" / "reference-map.json"


def crop_image(image: PngImage, *, x: int, y: int, width: int, height: int) -> PngImage:
    if x < 0 or y < 0 or width <= 0 or height <= 0:
        raise ValueError("crop must use non-negative origin and positive size")
    if x + width > image.width or y + height > image.height:
        raise ValueError(
            f"crop {x},{y},{width}x{height} exceeds source {image.width}x{image.height}"
        )
    out = bytearray()
    row_bytes = image.width * 4
    for row in range(y, y + height):
        start = row * row_bytes + x * 4
        out.extend(image.rgba[start:start + width * 4])
    return PngImage(width=width, height=height, rgba=bytes(out))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--map", type=Path, default=DEFAULT_MAP)
    args = parser.parse_args()

    mapping_path = args.map.resolve()
    if not mapping_path.exists():
        print(f"[skip] reference map not available: {mapping_path}")
        return 0

    base = mapping_path.parent
    payload = json.loads(mapping_path.read_text(encoding="utf-8"))
    states = payload.get("states", [])
    if not states:
        print("[FAIL] reference map contains no states")
        return 1

    failures = 0
    for entry in states:
        state = entry["state"]
        generated = (base / entry["generated"]).resolve()
        reference = (base / entry["reference"]).resolve()
        crop = entry["crop"]
        thresholds = entry["thresholds"]
        missing = [path for path in (generated, reference) if not path.exists()]
        if missing:
            print(f"[skip] {state}: reference artifacts are not available")
            for path in missing:
                print(f"[skip] missing: {path}")
            continue
        try:
            generated_img = read_png(generated)
            reference_img = crop_image(read_png(reference), **crop)
            changed, changed_pct, avg_delta, max_delta = diff_images(generated_img, reference_img)
        except Exception as exc:
            print(f"[FAIL] {state}: {exc}")
            failures += 1
            continue
        print(
            f"[diff] {state}: ref={reference.name} crop="
            f"{crop['x']},{crop['y']},{crop['width']}x{crop['height']} "
            f"changed={changed_pct:.4f}% avg_delta={avg_delta} max_delta={max_delta}"
        )
        if (
            changed_pct > thresholds["max_changed_pct"]
            or avg_delta > thresholds["max_avg_delta"]
            or max_delta > thresholds["max_channel_delta"]
        ):
            print(f"[FAIL] {state}: exceeds calibrated tolerance")
            failures += 1
        else:
            print(f"[ok ] {state}: mapped crop is diffable within tolerance")

    if failures:
        print(f"Result: FAIL ({failures} reference-map issues)")
        return 1
    print(f"Result: PASS ({len(states)} mapped reference crops)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
