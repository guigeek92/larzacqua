from __future__ import annotations

from src.infrastructure_mapper import build_infrastructure_graph, update_udi_fields_from_detections


def test_build_infrastructure_graph_creates_nodes():
    detections = [
        {
            "symbol": "pressure_reducer",
            "confidence": 0.92,
            "bounding_box": [10, 10, 40, 40],
            "page": 2,
            "site": "UDI 1",
        },
        {
            "symbol": "pipe",
            "confidence": 0.88,
            "bounding_box": [45, 15, 180, 35],
            "page": 2,
            "site": "UDI 1",
        },
    ]

    graph = build_infrastructure_graph(detections)

    assert len(graph["nodes"]) == 2
    assert any(edge["relation"] == "REGULATES_PRESSURE_ON" for edge in graph["edges"])


def test_update_udi_fields_from_detections_backfills_reducer_fields():
    result_json = {
        "presence_reducteurs_pression": None,
        "nombre_reducteurs_pression": None,
        "points_pression_reduction": [],
    }
    detections = [
        {
            "symbol": "pressure_reducer",
            "confidence": 0.9,
            "bounding_box": [20, 20, 50, 50],
            "page": 1,
            "site": "UDI 2",
        }
    ]

    update_udi_fields_from_detections(result_json, detections)

    assert result_json["presence_reducteurs_pression"] is True
    assert result_json["nombre_reducteurs_pression"] == 1
    assert result_json["points_pression_reduction"]
