from __future__ import annotations

from typing import Any


def normalize_symbol_detection(item: dict[str, Any]) -> dict[str, Any] | None:
    symbol = str(item.get("symbol") or "").strip()
    bbox = item.get("bounding_box")
    if not symbol or not isinstance(bbox, list) or len(bbox) != 4:
        return None

    try:
        x1, y1, x2, y2 = [float(v) for v in bbox]
    except (TypeError, ValueError):
        return None

    page = int(item.get("page") or 0)
    if page <= 0:
        page = 1

    return {
        "symbol": symbol,
        "confidence": float(item.get("confidence") or 0.0),
        "bounding_box": [x1, y1, x2, y2],
        "page": page,
        "site": str(item.get("site") or ""),
        "method": str(item.get("method") or ""),
    }
