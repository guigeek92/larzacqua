from __future__ import annotations

from app.streamlit_app import (
    is_udi_infrastructure_attachment_entry,
    is_udi_infrastructure_attachment_filename,
)


def test_infrastructure_attachment_detects_reservoir_file() -> None:
    assert is_udi_infrastructure_attachment_filename("CCLL-R3.1 Reservoir Labeil.pdf") is True


def test_infrastructure_attachment_detects_source_file() -> None:
    assert is_udi_infrastructure_attachment_filename("CCLL-S1 Source Font Vive.pdf") is True


def test_infrastructure_attachment_ignores_synoptic_file() -> None:
    assert is_udi_infrastructure_attachment_filename("Synoptique UDI 3 Beaume Boucart.pdf") is False


def test_infrastructure_attachment_entry_requires_udi_type() -> None:
    steu_entry = {"document_type": "steu", "filename": "Source Font Vive.pdf"}
    udi_entry = {"document_type": "udi", "filename": "Source Font Vive.pdf"}

    assert is_udi_infrastructure_attachment_entry(steu_entry) is False
    assert is_udi_infrastructure_attachment_entry(udi_entry) is True
