from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shutil


SYMBOL_KEYWORDS: dict[str, tuple[str, ...]] = {
    "pressure_reducer": ("rp", "prv", "reducteur", "regulateur"),
    "pressure_break_chamber": ("brise", "b.c", "bc", "altimetrique"),
    "valve": ("vanne",),
    "pump": ("pompe", "surpresseur"),
    "reservoir": ("reservoir", "reservoirs"),
    "source": ("source", "captage"),
    "meter": ("compteur",),
    "uv_treatment": ("uv",),
    "chlorine_treatment": ("chlore", "cl", "liquide"),
    "filtration": ("filtration",),
}


def _normalize_text(value: str) -> str:
    text = (value or "").strip().lower()
    text = text.replace("é", "e").replace("è", "e").replace("ê", "e")
    text = text.replace("à", "a").replace("â", "a")
    text = text.replace("î", "i").replace("ï", "i")
    text = text.replace("ô", "o")
    text = text.replace("û", "u").replace("ù", "u")
    text = text.replace("ç", "c")
    return re.sub(r"\s+", " ", text)


def _symbol_from_label(text: str) -> str | None:
    norm = f" {_normalize_text(text)} "
    for symbol, keywords in SYMBOL_KEYWORDS.items():
        for keyword in keywords:
            key = _normalize_text(keyword)
            if f" {key} " in norm or key in norm:
                return symbol
    return None


def _resolve_tesseract_cmd() -> str:
    env_value = ""
    try:
        import os

        env_value = os.getenv("TESSERACT_CMD", "").strip()
    except Exception:
        env_value = ""

    if env_value:
        if Path(env_value).exists():
            return env_value
        from_path = shutil.which(env_value)
        if from_path:
            return from_path

    from_system = shutil.which("tesseract")
    if from_system:
        return from_system

    for candidate in [
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
    ]:
        if Path(candidate).exists():
            return candidate

    return ""


def _extract_candidates_fallback(legend_path: Path, out_dir: Path, min_area: int, max_area: int) -> list[dict]:
    """Fallback extraction: global contour slicing (used only when OCR-guided extraction fails)."""
    import cv2  # type: ignore

    image = cv2.imread(str(legend_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return []

    blur = cv2.GaussianBlur(image, (3, 3), 0)
    edges = cv2.Canny(blur, 80, 180)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    out_dir.mkdir(parents=True, exist_ok=True)
    candidates: list[dict] = []
    idx = 0
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = int(w * h)
        if area < min_area or area > max_area:
            continue
        if h < 10 or w < 10 or w > 220 or h > 220:
            continue

        crop = image[max(0, y - 4) : min(image.shape[0], y + h + 4), max(0, x - 4) : min(image.shape[1], x + w + 4)]
        if crop.size == 0:
            continue

        out_name = f"cand_{idx:03d}.png"
        cv2.imwrite(str(out_dir / out_name), crop)
        candidates.append(
            {
                "file": out_name,
                "legend": legend_path.name,
                "symbol": "unknown",
                "bbox": [int(x), int(y), int(x + w), int(y + h)],
            }
        )
        idx += 1

    return candidates


def _extract_symbol_crop_near_label(image_gray, label_bbox: tuple[int, int, int, int]):
    import cv2  # type: ignore
    import numpy as np  # type: ignore

    x, y, w, h = label_bbox
    x0 = max(0, x - 150)
    x1 = max(0, x - 6)
    y0 = max(0, y - int(h * 0.8) - 8)
    y1 = min(image_gray.shape[0], y + int(h * 1.8) + 8)
    if x1 <= x0 or y1 <= y0:
        return None, None

    roi = image_gray[y0:y1, x0:x1]
    blur = cv2.GaussianBlur(roi, (3, 3), 0)
    _, binary = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (2, 2))
    binary = cv2.morphologyEx(binary, cv2.MORPH_OPEN, kernel, iterations=1)

    contours, _ = cv2.findContours(binary, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    best = None
    best_score = -1.0
    for contour in contours:
        cx, cy, cw, ch = cv2.boundingRect(contour)
        area = float(cw * ch)
        if area < 90 or area > 18000:
            continue
        aspect = float(cw / ch) if ch > 0 else 0.0
        if aspect < 0.25 or aspect > 3.5:
            continue
        # Prefer symbols near the label-side edge and close to label baseline.
        dist_to_right = abs((cx + cw) - roi.shape[1])
        center_y = cy + ch / 2.0
        baseline_y = (y - y0) + h / 2.0
        dist_to_baseline = abs(center_y - baseline_y)
        score = area - (dist_to_right * 12.0) - (dist_to_baseline * 8.0)
        if score > best_score:
            best_score = score
            best = (cx, cy, cw, ch)

    if best is None:
        return None, None

    bx, by, bw, bh = best
    pad = 3
    sx0 = max(0, bx - pad)
    sy0 = max(0, by - pad)
    sx1 = min(roi.shape[1], bx + bw + pad)
    sy1 = min(roi.shape[0], by + bh + pad)
    crop = roi[sy0:sy1, sx0:sx1]
    if crop.size == 0:
        return None, None

    global_bbox = [int(x0 + sx0), int(y0 + sy0), int(x0 + sx1), int(y0 + sy1)]
    return crop, global_bbox


def _extract_guided_templates(
    legend_path: Path,
    output_root: Path,
    max_templates_per_legend: int | None = None,
    one_per_line: bool = False,
) -> list[dict]:
    try:
        import cv2  # type: ignore
        import pytesseract  # type: ignore
    except Exception as exc:
        raise RuntimeError("OpenCV (cv2) and pytesseract are required for guided template bootstrap.") from exc

    tesseract_cmd = _resolve_tesseract_cmd()
    if tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    image = cv2.imread(str(legend_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return []

    ocr = pytesseract.image_to_data(image, lang="fra+eng", config="--oem 3 --psm 6", output_type=pytesseract.Output.DICT)
    n = len(ocr.get("text", []))
    saved: list[dict] = []
    counters: dict[str, int] = {}

    entries: list[dict] = []
    for i in range(n):
        txt = str(ocr["text"][i] or "").strip()
        if not txt:
            continue
        try:
            conf = float(ocr["conf"][i])
        except Exception:
            conf = -1.0
        if conf < 20.0:
            continue
        symbol = _symbol_from_label(txt)
        if symbol is None:
            continue

        try:
            block_num = int(ocr["block_num"][i])
            par_num = int(ocr["par_num"][i])
            line_num = int(ocr["line_num"][i])
        except Exception:
            block_num, par_num, line_num = 0, 0, i

        x = int(ocr["left"][i])
        y = int(ocr["top"][i])
        w = int(ocr["width"][i])
        h = int(ocr["height"][i])

        entries.append(
            {
                "symbol": symbol,
                "text": txt,
                "conf": conf,
                "bbox": (x, y, w, h),
                "line_key": (block_num, par_num, line_num),
            }
        )

    if one_per_line:
        best_per_line: dict[tuple[int, int, int], dict] = {}
        for entry in entries:
            key = entry["line_key"]
            existing = best_per_line.get(key)
            if existing is None or float(entry["conf"]) > float(existing["conf"]):
                best_per_line[key] = entry
        selected_entries = sorted(best_per_line.values(), key=lambda e: float(e["conf"]), reverse=True)
    else:
        selected_entries = sorted(entries, key=lambda e: float(e["conf"]), reverse=True)

    if isinstance(max_templates_per_legend, int) and max_templates_per_legend > 0:
        selected_entries = selected_entries[:max_templates_per_legend]

    for entry in selected_entries:
        symbol = str(entry["symbol"])
        txt = str(entry["text"])
        conf = float(entry["conf"])
        x, y, w, h = entry["bbox"]

        crop, bbox = _extract_symbol_crop_near_label(image, (x, y, w, h))
        if crop is None or bbox is None:
            continue

        symbol_dir = output_root / symbol
        symbol_dir.mkdir(parents=True, exist_ok=True)
        idx = counters.get(symbol, 0)
        counters[symbol] = idx + 1
        file_name = f"tpl_{legend_path.stem.replace(' ', '_').lower()}_{idx:03d}.png"
        out_path = symbol_dir / file_name
        cv2.imwrite(str(out_path), crop)

        saved.append(
            {
                "file": file_name,
                "legend": legend_path.name,
                "symbol": symbol,
                "label_text": txt,
                "label_confidence": conf,
                "bbox": bbox,
            }
        )

    return saved


def _extract_candidates(legend_path: Path, out_dir: Path, min_area: int, max_area: int) -> list[dict]:
    try:
        import cv2  # type: ignore
    except Exception as exc:
        raise RuntimeError("OpenCV (cv2) is required for template bootstrap.") from exc

    image = cv2.imread(str(legend_path), cv2.IMREAD_GRAYSCALE)
    if image is None:
        return []

    blur = cv2.GaussianBlur(image, (3, 3), 0)
    edges = cv2.Canny(blur, 80, 180)
    contours, _ = cv2.findContours(edges, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)

    out_dir.mkdir(parents=True, exist_ok=True)
    candidates: list[dict] = []
    idx = 0
    seen_boxes: list[tuple[int, int, int, int]] = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        area = int(w * h)
        if area < min_area or area > max_area:
            continue

        aspect = float(w / h) if h > 0 else 0.0
        if aspect < 0.35 or aspect > 2.8:
            continue

        # Skip likely text fragments.
        if h < 10 or w < 10:
            continue
        if w > 220 or h > 220:
            continue

        # Skip contours touching almost full image (frame/background artifacts).
        if w >= int(image.shape[1] * 0.9) and h >= int(image.shape[0] * 0.9):
            continue

        pad = 4
        x0 = max(0, x - pad)
        y0 = max(0, y - pad)
        x1 = min(image.shape[1], x + w + pad)
        y1 = min(image.shape[0], y + h + pad)

        # Deduplicate near-identical candidate boxes.
        is_duplicate = False
        for sx0, sy0, sx1, sy1 in seen_boxes:
            if abs(x0 - sx0) <= 3 and abs(y0 - sy0) <= 3 and abs(x1 - sx1) <= 3 and abs(y1 - sy1) <= 3:
                is_duplicate = True
                break
        if is_duplicate:
            continue
        seen_boxes.append((x0, y0, x1, y1))

        crop = image[y0:y1, x0:x1]
        if crop.size == 0:
            continue

        out_name = f"cand_{idx:03d}.png"
        out_path = out_dir / out_name
        cv2.imwrite(str(out_path), crop)
        candidates.append(
            {
                "file": out_name,
                "legend": legend_path.name,
                "bbox": [int(x0), int(y0), int(x1), int(y1)],
                "width": int(x1 - x0),
                "height": int(y1 - y0),
                "area": area,
            }
        )
        idx += 1

    return candidates


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap symbol templates from legend images.")
    parser.add_argument("--legend1", default="legende 1.JPG", help="Path to legend 1 image")
    parser.add_argument("--legend2", default="legende 2.JPG", help="Path to legend 2 image")
    parser.add_argument("--output", default="data/templates_symbols", help="Output directory for templates")
    parser.add_argument("--min-area", type=int, default=120, help="Minimum contour area")
    parser.add_argument("--max-area", type=int, default=18000, help="Maximum contour area")
    parser.add_argument(
        "--mode",
        choices=["guided", "fallback"],
        default="guided",
        help="guided=OCR labels + adjacent symbol crop, fallback=global contour candidates",
    )
    parser.add_argument("--max-per-legend1", type=int, default=15, help="Maximum templates extracted from legend 1")
    args = parser.parse_args()

    workspace_root = Path(__file__).resolve().parents[1]
    legend_paths = [workspace_root / args.legend1, workspace_root / args.legend2]
    output_root = workspace_root / args.output

    all_candidates: list[dict] = []
    for legend_path in legend_paths:
        if not legend_path.exists():
            print(f"[WARN] Missing legend image: {legend_path}")
            continue

        if args.mode == "guided":
            lower_name = legend_path.name.lower()
            is_legend_1 = "legende 1" in lower_name or "legend 1" in lower_name or "image1" in lower_name
            candidates = _extract_guided_templates(
                legend_path,
                output_root,
                max_templates_per_legend=args.max_per_legend1 if is_legend_1 else None,
                one_per_line=is_legend_1,
            )
            if not candidates:
                # Auto-fallback for very noisy OCR cases.
                legend_out = output_root / "candidates" / legend_path.stem.replace(" ", "_").lower()
                candidates = _extract_candidates_fallback(legend_path, legend_out, args.min_area, args.max_area)
        else:
            legend_out = output_root / "candidates" / legend_path.stem.replace(" ", "_").lower()
            candidates = _extract_candidates_fallback(legend_path, legend_out, args.min_area, args.max_area)

        all_candidates.extend(candidates)
        if args.mode == "guided":
            print(f"[INFO] {legend_path.name}: extracted {len(candidates)} guided templates")
        else:
            print(f"[INFO] {legend_path.name}: extracted {len(candidates)} fallback candidates")

    metadata_path = output_root / "templates_metadata.json"
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(all_candidates, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\nNext step:")
    print("1. Review generated templates in data/templates_symbols/<symbol>/")
    print("2. Remove bad templates manually if needed")
    print("3. Run extraction; template-bank detections are loaded automatically")


if __name__ == "__main__":
    main()
