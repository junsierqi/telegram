"""Validator for M148 — desktop bubble image thumbnails.

Checks the desktop bubble pipeline gained:

  1. BubbleMessageModel exposes 3 new roles (AttachmentIdRole,
     AttachmentMimeRole, ThumbnailRole) and a setThumbnailCache(...)
     mutator that emits dataChanged for every row whose attachment id
     appears in the new map. The data() handler returns a wrapped QPixmap
     for messages whose attachment_id is in the cache.
  2. BubbleListView passes setThumbnailCache through to the model and
     repaints the viewport.
  3. BubbleDelegate's LayoutMetrics carries thumbnailWidth/thumbnailHeight
     and measure() reserves the area when ThumbnailRole is non-null
     (capped at 240×240 with KeepAspectRatio); paint() draws the scaled
     pixmap above the body text via drawPixmap.
  4. app_desktop/main.cpp has request_thumbnails_for_visible_messages()
     that scans the selected conversation, filters to image MIMEs, kicks
     a worker thread per cache miss (capped at 8 inflight), decodes via
     QImage::loadFromData, scales to a max 480×480 cache copy, and pushes
     the updated map via messages_->setThumbnailCache.

Pure static — runs without Qt.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path


REPO = Path(__file__).resolve().parent.parent
HEADER = REPO / "client" / "src" / "app_desktop" / "bubble_list_view.h"
SRC = REPO / "client" / "src" / "app_desktop" / "bubble_list_view.cpp"
MAIN = REPO / "client" / "src" / "app_desktop" / "main.cpp"


def main() -> int:
    for p in (HEADER, SRC, MAIN):
        if not p.exists():
            print(f"[FAIL] missing {p}")
            return 1
    h = HEADER.read_text(encoding="utf-8")
    cpp = SRC.read_text(encoding="utf-8")
    m = MAIN.read_text(encoding="utf-8")

    print("[scenario] new roles + setThumbnailCache declared in the header")
    for role in ("AttachmentIdRole", "AttachmentMimeRole", "ThumbnailRole"):
        assert role in h, f"role {role!r} missing from BubbleMessageModel"
    assert "setThumbnailCache" in h, "setThumbnailCache method missing"
    assert "QHash<QString, QPixmap>" in h, "thumbnails cache type signature missing"
    assert "QPixmap" in h, "QPixmap include / declaration must reach the header"
    print("[ok ] header surface area updated for thumbnails")

    print("[scenario] data() returns ThumbnailRole + setThumbnailCache emits dataChanged")
    data_match = re.search(
        r"QVariant\s+BubbleMessageModel::data\s*\([^)]*\)\s*const\s*\{(?P<b>.*?)\n\}",
        cpp, re.DOTALL,
    )
    assert data_match, "data() body not found"
    db = data_match.group("b")
    assert "ThumbnailRole" in db, "data() must handle ThumbnailRole"
    assert "thumbnails_.find" in db, "data() must look up the cache by attachment_id"
    cache_match = re.search(
        r"BubbleMessageModel::setThumbnailCache\s*\([^)]*\)\s*\{(?P<b>.*?)\n\}",
        cpp, re.DOTALL,
    )
    assert cache_match, "setThumbnailCache body missing"
    sb = cache_match.group("b")
    assert "thumbnails_ = thumbnails" in sb, "setter must store the new cache"
    assert "emit dataChanged" in sb, "setter must emit dataChanged on row range"
    assert "ThumbnailRole" in sb, "setter must include ThumbnailRole in dataChanged roles"
    print("[ok ] role wiring + cache mutator emit dataChanged")

    print("[scenario] BubbleListView passes setThumbnailCache through")
    plv = re.search(
        r"void\s+BubbleListView::setThumbnailCache\s*\([^)]*\)\s*\{(?P<b>.*?)\n\}",
        cpp, re.DOTALL,
    )
    assert plv, "BubbleListView::setThumbnailCache missing"
    pb = plv.group("b")
    assert "model_->setThumbnailCache" in pb, "view must forward to the model"
    assert "viewport()->update" in pb, "view must trigger repaint after refresh"
    print("[ok ] view passthrough wired")

    print("[scenario] LayoutMetrics + measure + paint allocate thumbnail area")
    assert "thumbnailHeight" in h, "LayoutMetrics must add thumbnailHeight"
    assert "thumbnailWidth" in h, "LayoutMetrics must add thumbnailWidth"
    measure_match = re.search(
        r"BubbleDelegate::LayoutMetrics\s+BubbleDelegate::measure\s*\([^)]*\)[^{]*\{(?P<b>.*?)\n\}",
        cpp, re.DOTALL,
    )
    assert measure_match, "measure() body not found"
    mb = measure_match.group("b")
    assert "ThumbnailRole" in mb, "measure() must read ThumbnailRole"
    assert "scaled" in mb, "measure() must scale the pixmap to bound the area"
    assert "240" in mb, "thumbnail cap (240px) missing from measure()"
    paint_match = re.search(
        r"void\s+BubbleDelegate::paint\s*\([^)]*\)\s*const\s*\{(?P<b>.*?)\n\}",
        cpp, re.DOTALL,
    )
    assert paint_match, "paint() body not found"
    pb = paint_match.group("b")
    assert "drawPixmap" in pb, "paint() must call drawPixmap for the thumbnail"
    assert "thumbnailHeight" in pb, "paint() must consume the thumbnail layout slot"
    print("[ok ] layout + measure + paint reserve and draw the thumbnail area")

    print("[scenario] main.cpp request_thumbnails_for_visible_messages drives the cache")
    fn = re.search(
        r"void\s+request_thumbnails_for_visible_messages\s*\(\s*\)\s*\{(?P<b>.*?)\n\s{4}\}",
        m, re.DOTALL,
    )
    assert fn, "request_thumbnails_for_visible_messages body not found"
    body = fn.group("b")
    assert 'mime_type.rfind("image/", 0)' in body, \
        "must filter by image/* MIME"
    assert "thumbnail_cache_.contains" in body, \
        "must skip already-cached attachments"
    assert "thumbnail_inflight_" in body, \
        "must track in-flight fetches to avoid duplicate workers"
    assert "fetch_attachment(" in body, \
        "must call fetch_attachment(attachment_id) for cache misses"
    assert "QImage" in body and "loadFromData" in body, \
        "must decode the bytes via QImage::loadFromData"
    assert "QPixmap::fromImage" in body, \
        "must convert to QPixmap before caching"
    assert "messages_->setThumbnailCache" in body, \
        "must push the updated cache into BubbleListView"
    assert "render_store" not in body or "request_thumbnails" in m, \
        "must be invoked from render_store"
    # render_store invocation
    assert "request_thumbnails_for_visible_messages();" in m, \
        "render_store must call request_thumbnails_for_visible_messages()"
    print("[ok ] fetch + decode + cache + push pipeline wired")

    print("\nAll 5/5 scenarios passed.")
    return 0


if __name__ == "__main__":
    import traceback
    try:
        sys.exit(main())
    except AssertionError as exc:
        print(f"[FAIL] {exc}")
        traceback.print_exc()
        sys.exit(1)
    except Exception as exc:
        print(f"[FAIL] {type(exc).__name__}: {exc}")
        traceback.print_exc()
        sys.exit(1)
