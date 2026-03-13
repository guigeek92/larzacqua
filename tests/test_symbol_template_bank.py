from __future__ import annotations

from pathlib import Path

import pytest

from src.symbol_detection import detect_symbols_from_template_bank


try:
    import cv2  # type: ignore

    HAS_CV2 = True
except Exception:
    HAS_CV2 = False


@pytest.mark.skipif(not HAS_CV2, reason="cv2 is required")
def test_detect_symbols_from_template_bank_finds_simple_match(tmp_path: Path) -> None:
    import numpy as np  # type: ignore

    image = np.zeros((120, 120, 3), dtype=np.uint8)
    cv2.rectangle(image, (40, 50), (60, 70), (255, 255, 255), thickness=-1)

    templates_root = tmp_path / "templates"
    symbol_dir = templates_root / "pressure_reducer"
    symbol_dir.mkdir(parents=True, exist_ok=True)

    template = np.zeros((24, 24), dtype=np.uint8)
    cv2.rectangle(template, (4, 4), (20, 20), 255, thickness=-1)
    cv2.imwrite(str(symbol_dir / "t1.png"), template)

    detections = detect_symbols_from_template_bank(
        image_bgr=image,
        templates_dir=templates_root,
        page=1,
        site="UDI TEST",
        threshold=0.7,
        scales=(1.0,),
    )

    assert detections
    assert any(d.get("symbol") == "pressure_reducer" for d in detections)
