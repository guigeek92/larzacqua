from src.ai_extraction import _safe_extract_json_and_description


def test_safe_extract_handles_empty_response() -> None:
    parsed, description, warning = _safe_extract_json_and_description("")

    assert parsed == {}
    assert description == ""
    assert warning == "Réponse IA vide."


def test_safe_extract_handles_malformed_json() -> None:
    malformed = '{"nom_udi": "UDI 9"\n "debit_m3_j": 1200}'
    parsed, description, warning = _safe_extract_json_and_description(malformed)

    assert parsed == {}
    assert description == ""
    assert warning is not None
    assert "JSON IA invalide" in warning


def test_safe_extract_parses_valid_json_and_description() -> None:
    raw = '{"nom_udi": "UDI test", "debit_m3_j": 42}\nDescription: test ok'
    parsed, description, warning = _safe_extract_json_and_description(raw)

    assert parsed.get("nom_udi") == "UDI test"
    assert parsed.get("debit_m3_j") == 42
    assert description == "test ok"
    assert warning is None
