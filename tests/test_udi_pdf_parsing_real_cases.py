from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path

import pytest

from src.ai_extraction import _extract_udi_fields_from_text
from src.pdf_parser import extract_text_from_pdf


FIXTURE_PATH = Path(__file__).parent / "fixtures" / "udi_real_cases.json"
CRITICAL_FIELDS = [
    "nom_udi",
    "debit_m3_j",
    "volume_reservoir_m3",
    "denivele_source_reservoir_m",
    "presence_reducteurs_pression",
]

# Per-case expectations based on real OCR-like snippets.
CASE_EXPECTATIONS = {
    "udi_01_soulages": {"name_contains": "Soulages", "min_present": 5},
    "udi_02_vernede_ocr": {"name_contains": "Vernede", "min_present": 4},
    "udi_03_lambeyran_columns": {"name_contains": "Lambeyran", "min_present": 5},
    "udi_04_beaume": {"name_contains": "Beaume", "min_present": 4},
    "udi_05_range_debit": {"name_contains": "Crozes", "min_present": 5},
    "udi_06_pressure_head": {"name_contains": "Ventajou", "min_present": 3},
    "udi_07_multi_sites": {"name_contains": "UDI", "min_present": 5},
    "udi_08_volume_reference": {"name_contains": "Le Bosc", "min_present": 4},
    "udi_09_negative_head": {"name_contains": "Test Bas", "min_present": 5},
    "udi_10_noisy_labels": {"name_contains": "Puech", "min_present": 4},
}


def _present(value) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return len(value) > 0
    return True


def _make_pdf_bytes(text: str) -> bytes:
    reportlab_canvas = pytest.importorskip("reportlab.pdfgen.canvas").Canvas
    letter = pytest.importorskip("reportlab.lib.pagesizes").letter

    stream = BytesIO()
    canvas = reportlab_canvas(stream, pagesize=letter)
    width, height = letter
    y = height - 40
    for raw_line in text.split("\n"):
        line = raw_line[:140]
        canvas.drawString(40, y, line)
        y -= 14
        if y < 40:
            canvas.showPage()
            y = height - 40
    canvas.save()
    return stream.getvalue()


@pytest.fixture(scope="module")
def udi_cases() -> list[dict[str, str]]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


@pytest.mark.parametrize("case", json.loads(FIXTURE_PATH.read_text(encoding="utf-8")), ids=lambda c: c["id"])
def test_udi_extraction_from_generated_pdf(case: dict[str, str]) -> None:
    pdf_bytes = _make_pdf_bytes(case["text"])
    extracted_text = extract_text_from_pdf(pdf_bytes)

    assert extracted_text.strip(), f"No text extracted for {case['id']}"

    parsed = _extract_udi_fields_from_text(extracted_text)
    expected = CASE_EXPECTATIONS[case["id"]]

    name = str(parsed.get("nom_udi") or "")
    assert expected["name_contains"].lower() in name.lower()

    present_count = sum(1 for field in CRITICAL_FIELDS if _present(parsed.get(field)))
    assert present_count >= expected["min_present"], (
        f"{case['id']} critical fields too low: {present_count}/{len(CRITICAL_FIELDS)}"
    )


def test_critical_field_coverage_threshold(udi_cases: list[dict[str, str]]) -> None:
    total_slots = len(udi_cases) * len(CRITICAL_FIELDS)
    found_slots = 0

    for case in udi_cases:
        pdf_bytes = _make_pdf_bytes(case["text"])
        extracted_text = extract_text_from_pdf(pdf_bytes)
        parsed = _extract_udi_fields_from_text(extracted_text)
        found_slots += sum(1 for field in CRITICAL_FIELDS if _present(parsed.get(field)))

    coverage = (found_slots / total_slots) * 100 if total_slots else 0.0
    # Target after parser hardening.
    assert coverage >= 88.0, f"Coverage too low: {coverage:.1f}%"
