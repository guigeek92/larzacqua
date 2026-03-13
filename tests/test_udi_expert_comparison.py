from __future__ import annotations

import json
import unicodedata
from io import BytesIO
from pathlib import Path

import pytest

from app.streamlit_app import build_hydro_summary
from src.ai_extraction import _detect_legend_equipment_from_pdf, _extract_udi_fields_from_text, _slice_text_to_forced_udi_section
from src.pdf_parser import extract_text_from_pdf


TEXT_CASES_PATH = Path(__file__).parent / "fixtures" / "udi_real_cases.json"
EXPERT_CASES_PATH = Path(__file__).parent / "fixtures" / "udi_expert_ground_truth.json"


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


def _norm_text(value: str | None) -> str:
    base = unicodedata.normalize("NFKD", value or "")
    base = "".join(ch for ch in base if not unicodedata.combining(ch))
    return " ".join(base.lower().split())


def _numeric_match(predicted: object, expected: float | None, rel_tol: float = 0.08, abs_tol: float = 5.0) -> bool:
    if expected is None:
        return predicted is None
    if not isinstance(predicted, (int, float)):
        return False
    gap = abs(float(predicted) - float(expected))
    max_gap = max(abs_tol, abs(float(expected)) * rel_tol)
    return gap <= max_gap


def _presence_match(predicted: object, expected: bool | None) -> bool:
    if expected is None:
        return predicted is None
    return predicted is expected


def _build_comparison_metrics(pred: dict, expected: dict) -> tuple[float, list[str]]:
    checks: list[tuple[str, bool]] = []
    mismatches: list[str] = []

    expected_name = _norm_text(expected.get("nom_udi_contains"))
    predicted_name = _norm_text(str(pred.get("nom_udi") or ""))
    ok_name = bool(expected_name and expected_name in predicted_name)
    checks.append(("nom_udi", ok_name))
    if not ok_name:
        mismatches.append(f"nom_udi attendu~'{expected.get('nom_udi_contains')}', obtenu='{pred.get('nom_udi')}'")

    for field in ("debit_m3_j", "volume_reservoir_m3", "denivele_source_reservoir_m"):
        ok_num = _numeric_match(pred.get(field), expected.get(field))
        checks.append((field, ok_num))
        if not ok_num:
            mismatches.append(f"{field} attendu={expected.get(field)}, obtenu={pred.get(field)}")

    ok_reducer = _presence_match(pred.get("presence_reducteurs_pression"), expected.get("presence_reducteurs_pression"))
    checks.append(("presence_reducteurs_pression", ok_reducer))
    if not ok_reducer:
        mismatches.append(
            "presence_reducteurs_pression "
            f"attendu={expected.get('presence_reducteurs_pression')}, obtenu={pred.get('presence_reducteurs_pression')}"
        )

    # Also verify what is shown in the UI summary remains coherent with extracted values.
    summary = " | ".join(build_hydro_summary(pred, "udi"))
    summary_norm = _norm_text(summary)

    if isinstance(pred.get("debit_m3_j"), (int, float)):
        ui_flow_ok = "debit estime" in summary_norm
        checks.append(("ui_debit_visibility", ui_flow_ok))
        if not ui_flow_ok:
            mismatches.append("affichage: debit estime absent du resume")

    if pred.get("presence_reducteurs_pression") is True:
        ui_reducer_ok = "reducteurs de pression : presents" in summary_norm
        checks.append(("ui_reducer_visibility", ui_reducer_ok))
        if not ui_reducer_ok:
            mismatches.append("affichage: reducteurs presents non visibles")

    total = len(checks)
    passed = sum(1 for _, ok in checks if ok)
    score = passed / total if total else 0.0
    return score, mismatches


@pytest.fixture(scope="module")
def comparison_cases() -> list[dict]:
    text_cases = json.loads(TEXT_CASES_PATH.read_text(encoding="utf-8"))
    expert_cases = json.loads(EXPERT_CASES_PATH.read_text(encoding="utf-8"))

    text_by_id = {case["id"]: case for case in text_cases}
    merged: list[dict] = []
    for case in expert_cases:
        case_id = case["id"]
        if case_id not in text_by_id:
            raise AssertionError(f"Case id missing in text fixture: {case_id}")
        merged.append({"id": case_id, "text": text_by_id[case_id]["text"], "expert": case})
    return merged


@pytest.mark.parametrize("case", json.loads(EXPERT_CASES_PATH.read_text(encoding="utf-8")), ids=lambda c: c["id"])
def test_udi_case_alignment_with_expert_reference(case: dict) -> None:
    text_cases = json.loads(TEXT_CASES_PATH.read_text(encoding="utf-8"))
    text_by_id = {entry["id"]: entry["text"] for entry in text_cases}
    text = text_by_id[case["id"]]

    pdf_bytes = _make_pdf_bytes(text)
    parsed_text = extract_text_from_pdf(pdf_bytes)
    parsed = _extract_udi_fields_from_text(parsed_text)

    score, mismatches = _build_comparison_metrics(parsed, case)
    assert score >= 0.60, f"{case['id']} score={score:.2f} mismatches={mismatches}"


def test_udi_global_alignment_score(comparison_cases: list[dict]) -> None:
    scores: list[float] = []
    mismatch_report: dict[str, list[str]] = {}

    for case in comparison_cases:
        pdf_bytes = _make_pdf_bytes(case["text"])
        parsed_text = extract_text_from_pdf(pdf_bytes)
        parsed = _extract_udi_fields_from_text(parsed_text)

        score, mismatches = _build_comparison_metrics(parsed, case["expert"])
        scores.append(score)
        if mismatches:
            mismatch_report[case["id"]] = mismatches

    global_score = sum(scores) / len(scores) if scores else 0.0
    assert global_score >= 0.78, f"Global expert-alignment too low: {global_score:.2%} | mismatches={mismatch_report}"


def test_reducer_detection_ignores_isolated_rp_noise() -> None:
    text = """
    Synoptique UDI 20 - Test Bruit
    Mesures pression amont 8.2 bar
    R P
    Source 600 m NGF
    Reservoir principal 560 m NGF 150 m3
    """
    parsed = _extract_udi_fields_from_text(text)
    assert parsed.get("presence_reducteurs_pression") is False
    assert parsed.get("nombre_reducteurs_pression") in (None, 0)


def test_reducer_detection_accepts_contextual_abbreviation() -> None:
    text = """
    Synoptique UDI 21 - Test RP
    RP principal pression aval
    Source 640 m NGF
    Reservoir 590 m NGF 200 m3
    """
    parsed = _extract_udi_fields_from_text(text)
    assert parsed.get("presence_reducteurs_pression") is True
    assert isinstance(parsed.get("nombre_reducteurs_pression"), int)
    assert int(parsed.get("nombre_reducteurs_pression")) >= 1


def test_legend_detection_marks_rp_and_brise_charge_presence() -> None:
    text = """
    Synoptique UDI 22 - Lavalette
    LEGENDE
    O RP
    O B.C
    Reservoir principal 610 m NGF
    """
    pdf_bytes = _make_pdf_bytes(text)
    legend = _detect_legend_equipment_from_pdf(pdf_bytes)

    assert legend.get("has_reducer") is True
    assert legend.get("has_brise_charge") is True
    assert int(legend.get("legend_reducer_count") or 0) >= 1
    assert int(legend.get("legend_brise_charge_count") or 0) >= 1


def test_dense_ocr_like_udi_keeps_strong_signed_head() -> None:
    text = """
    UDI 7
    Source Soulages TN : 487m NGF 200m NGF 201m NGF 202m NGF 203m NGF 204m NGF 205m NGF 206m NGF 207m NGF 208m NGF 209m NGF 210m NGF
    Reservoir de Soulages TN : 421m NGF
    Source de la Vernede TN : 356m NGF Reservoir de la Vernede TN : 352m NGF
    """

    parsed = _extract_udi_fields_from_text(text)

    # The strongest source->reservoir pair is Soulages: 487 - 421 = 66 m.
    assert parsed.get("denivele_source_reservoir_m") == pytest.approx(66.0)
    assert parsed.get("hauteur_chute_estimee_m") == pytest.approx(66.0)


def test_forced_udi_segment_ignores_other_udi_blocks() -> None:
    text = """
    UDI 7 - Soulages
    Source de Soulages TN : 487 m NGF
    Reservoir de Soulages TN : 421 m NGF
    UDI 8 - Vernede
    Source de la Vernede TN : 356 m NGF
    Reservoir de la Vernede TN : 352 m NGF
    """

    sliced = _slice_text_to_forced_udi_section(text, "7")
    parsed = _extract_udi_fields_from_text(sliced)

    assert "UDI 8" not in sliced
    assert parsed.get("denivele_source_reservoir_m") == pytest.approx(66.0)
    assert parsed.get("hauteur_chute_estimee_m") == pytest.approx(66.0)
