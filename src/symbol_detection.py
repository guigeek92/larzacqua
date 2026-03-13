from __future__ import annotations

from pathlib import Path
from typing import Any


def _iou(box_a: list[float], box_b: list[float]) -> float:
    ax1, ay1, ax2, ay2 = box_a
    bx1, by1, bx2, by2 = box_b
    inter_x1 = max(ax1, bx1)
    inter_y1 = max(ay1, by1)
    inter_x2 = min(ax2, bx2)
    inter_y2 = min(ay2, by2)
    inter_w = max(0.0, inter_x2 - inter_x1)
    inter_h = max(0.0, inter_y2 - inter_y1)
    inter_area = inter_w * inter_h
    if inter_area <= 0.0:
        return 0.0
    area_a = max(0.0, ax2 - ax1) * max(0.0, ay2 - ay1)
    area_b = max(0.0, bx2 - bx1) * max(0.0, by2 - by1)
    union = area_a + area_b - inter_area
    if union <= 0.0:
        return 0.0
    return inter_area / union


def _nms(detections: list[dict[str, Any]], iou_threshold: float = 0.3) -> list[dict[str, Any]]:
    ordered = sorted(detections, key=lambda d: float(d.get("confidence") or 0.0), reverse=True)
    selected: list[dict[str, Any]] = []
    for candidate in ordered:
        candidate_bbox = candidate.get("bounding_box")
        if not isinstance(candidate_bbox, list) or len(candidate_bbox) != 4:
            continue
        keep = True
        for chosen in selected:
            chosen_bbox = chosen.get("bounding_box")
            if not isinstance(chosen_bbox, list) or len(chosen_bbox) != 4:
                continue
            if _iou(candidate_bbox, chosen_bbox) >= iou_threshold:
                keep = False
                break
        if keep:
            selected.append(candidate)
    return selected


def detect_symbol_template_opencv(
    image_bgr: Any,
    template_bgr: Any,
    symbol_name: str,
    page: int,
    site: str,
    threshold: float = 0.78,
) -> list[dict[str, Any]]:
    """Minimal OpenCV template-matching detector for one symbol class."""
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception:
        return []

    if image_bgr is None or template_bgr is None:
        return []

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    tpl = cv2.cvtColor(template_bgr, cv2.COLOR_BGR2GRAY)

    gray = cv2.GaussianBlur(gray, (3, 3), 0)
    tpl = cv2.GaussianBlur(tpl, (3, 3), 0)

    res = cv2.matchTemplate(gray, tpl, cv2.TM_CCOEFF_NORMED)
    ys, xs = np.where(res >= threshold)
    h, w = tpl.shape[:2]

    detections: list[dict[str, Any]] = []
    for x, y in zip(xs, ys):
        conf = float(res[y, x])
        detections.append(
            {
                "symbol": symbol_name,
                "confidence": round(conf, 4),
                "bounding_box": [float(x), float(y), float(x + w), float(y + h)],
                "page": int(page),
                "site": site,
                "method": "opencv_template",
            }
        )
    return detections


def infer_symbols_yolo(
    image_path: str | Path,
    model_path: str | Path,
    page: int,
    site: str,
    conf: float = 0.25,
    iou: float = 0.5,
) -> list[dict[str, Any]]:
    """YOLO inference helper returning standardized detections."""
    try:
        from ultralytics import YOLO  # type: ignore
    except Exception:
        return []

    model = YOLO(str(model_path))
    results = model.predict(str(image_path), conf=conf, iou=iou, verbose=False)
    if not results:
        return []

    detections: list[dict[str, Any]] = []
    result = results[0]
    names = result.names
    for box in result.boxes:
        cls_id = int(box.cls.item())
        score = float(box.conf.item())
        x1, y1, x2, y2 = [float(v) for v in box.xyxy[0].tolist()]
        detections.append(
            {
                "symbol": str(names.get(cls_id, cls_id)),
                "confidence": round(score, 4),
                "bounding_box": [x1, y1, x2, y2],
                "page": int(page),
                "site": site,
                "method": "yolo",
                "model_name": Path(model_path).stem,
            }
        )
    return detections


def detect_symbols_from_template_bank(
    image_bgr: Any,
    templates_dir: str | Path,
    page: int,
    site: str,
    threshold: float = 0.78,
    scales: tuple[float, ...] = (0.85, 1.0, 1.15),
) -> list[dict[str, Any]]:
    """Detect symbols using a template bank structured as templates_dir/<symbol>/*.png."""
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception:
        return []

    if image_bgr is None:
        return []

    root = Path(templates_dir)
    if not root.exists() or not root.is_dir():
        return []

    gray = cv2.cvtColor(image_bgr, cv2.COLOR_BGR2GRAY)
    all_detections: list[dict[str, Any]] = []

    for symbol_dir in root.iterdir():
        if not symbol_dir.is_dir():
            continue
        symbol_name = symbol_dir.name.strip()
        if not symbol_name:
            continue

        symbol_dets: list[dict[str, Any]] = []
        template_paths = sorted(
            [p for p in symbol_dir.iterdir() if p.suffix.lower() in {".png", ".jpg", ".jpeg"}]
        )
        for template_path in template_paths:
            tpl = cv2.imread(str(template_path), cv2.IMREAD_GRAYSCALE)
            if tpl is None:
                continue

            for scale in scales:
                if scale <= 0.0:
                    continue
                if scale == 1.0:
                    scaled_tpl = tpl
                else:
                    scaled_tpl = cv2.resize(tpl, dsize=None, fx=scale, fy=scale, interpolation=cv2.INTER_LINEAR)
                h, w = scaled_tpl.shape[:2]
                if h < 8 or w < 8:
                    continue
                if h >= gray.shape[0] or w >= gray.shape[1]:
                    continue

                result = cv2.matchTemplate(gray, scaled_tpl, cv2.TM_CCOEFF_NORMED)
                ys, xs = np.where(result >= threshold)
                for x, y in zip(xs, ys):
                    confidence = float(result[y, x])
                    symbol_dets.append(
                        {
                            "symbol": symbol_name,
                            "confidence": round(confidence, 4),
                            "bounding_box": [float(x), float(y), float(x + w), float(y + h)],
                            "page": int(page),
                            "site": site,
                            "method": "template_bank",
                        }
                    )

        all_detections.extend(_nms(symbol_dets, iou_threshold=0.3))

    return all_detections
