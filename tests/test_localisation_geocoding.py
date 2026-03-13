from __future__ import annotations

from app.streamlit_app import _build_geocoding_queries, _is_incoherent_geocode_result


def test_build_geocoding_queries_includes_schema_site_and_reservoir() -> None:
    result_json = {
        "nom_udi": "UDI 3 Beaume Boucart",
        "localisation": "Celles",
        "communes": ["Celles"],
        "sites_udi": [{"site": "UDI 3 Beaume Boucart"}],
        "reservoirs_udi": [{"reservoir": "Reservoir Labeil"}],
    }

    queries = _build_geocoding_queries("Site UDI", result_json)

    assert any("Reservoir Labeil, Celles" in q for q in queries)
    assert any("Reservoir Labeil, Herault, France" in q for q in queries)


def test_incoherent_geocode_result_is_rejected() -> None:
    query = "Reservoir Labeil, Celles"
    display_name = "Avenue de Paris, Paris, Ile-de-France, France"

    assert _is_incoherent_geocode_result(query, display_name) is True


def test_coherent_geocode_result_is_accepted() -> None:
    query = "Reservoir Labeil, Celles"
    display_name = "Reservoir du Labeil, Celles, Lodeve, Herault, Occitanie, France"

    assert _is_incoherent_geocode_result(query, display_name) is False
