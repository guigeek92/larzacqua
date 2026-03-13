from __future__ import annotations

from math import hypot
from typing import Any

SYMBOL_TO_ENTITY = {
    "pressure_reducer": "PressureReducer",
    "pressure_break_chamber": "PressureBreakChamber",
    "valve": "Valve",
    "pump": "Pump",
    "reservoir": "Reservoir",
    "pipe": "PipeSegment",
    "sensor": "Sensor",
}


def _center(bbox: list[float]) -> tuple[float, float]:
    return ((bbox[0] + bbox[2]) / 2.0, (bbox[1] + bbox[3]) / 2.0)


def _safe_bbox(value: Any) -> list[float] | None:
    if not isinstance(value, list) or len(value) != 4:
        return None
    try:
        return [float(value[0]), float(value[1]), float(value[2]), float(value[3])]
    except (TypeError, ValueError):
        return None


def build_infrastructure_graph(symbol_detections: list[dict[str, Any]]) -> dict[str, Any]:
    """Convert symbol detections into a lightweight infrastructure graph."""
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    for idx, det in enumerate(symbol_detections):
        if not isinstance(det, dict):
            continue
        symbol = str(det.get("symbol") or "").strip().lower()
        bbox = _safe_bbox(det.get("bounding_box"))
        if not symbol or bbox is None:
            continue
        node = {
            "id": f"n{idx + 1}",
            "type": SYMBOL_TO_ENTITY.get(symbol, symbol.title().replace("_", "")),
            "symbol": symbol,
            "page": int(det.get("page") or 0),
            "site": str(det.get("site") or ""),
            "bbox": bbox,
            "confidence": float(det.get("confidence") or 0.0),
        }
        nodes.append(node)

    # Simple spatial relation rule: symbols close to a pipe on same page/site are linked.
    pipe_nodes = [n for n in nodes if n.get("symbol") == "pipe"]
    for node in nodes:
        if node.get("symbol") == "pipe":
            continue
        for pipe in pipe_nodes:
            if node.get("page") != pipe.get("page"):
                continue
            if (node.get("site") or "") != (pipe.get("site") or ""):
                continue
            cx1, cy1 = _center(node["bbox"])
            cx2, cy2 = _center(pipe["bbox"])
            dist = hypot(cx1 - cx2, cy1 - cy2)
            if dist > 180.0:
                continue
            relation = "CONNECTED_TO"
            if node.get("symbol") == "pressure_reducer":
                relation = "REGULATES_PRESSURE_ON"
            elif node.get("symbol") == "pump":
                relation = "FEEDS"
            elif node.get("symbol") == "sensor":
                relation = "MONITORS"
            edges.append(
                {
                    "source": node["id"],
                    "target": pipe["id"],
                    "relation": relation,
                    "confidence": round(min(node["confidence"], pipe["confidence"]), 4),
                }
            )

    return {
        "nodes": nodes,
        "edges": edges,
    }


def update_udi_fields_from_detections(result_json: dict[str, Any], symbol_detections: list[dict[str, Any]]) -> None:
    """Backfill existing UDI fields from standardized detections without breaking API compatibility."""
    if not isinstance(result_json, dict):
        return

    reducer_dets = [d for d in symbol_detections if str(d.get("symbol") or "") == "pressure_reducer"]
    brise_dets = [d for d in symbol_detections if str(d.get("symbol") or "") == "pressure_break_chamber"]

    if reducer_dets:
        result_json["presence_reducteurs_pression"] = True
        existing = result_json.get("nombre_reducteurs_pression")
        reducer_count = len(reducer_dets)
        if isinstance(existing, (int, float)):
            result_json["nombre_reducteurs_pression"] = max(int(existing), reducer_count)
        else:
            result_json["nombre_reducteurs_pression"] = reducer_count

        points = result_json.get("points_pression_reduction")
        if not isinstance(points, list):
            points = []
        for det in reducer_dets:
            page = int(det.get("page") or 0)
            bbox = det.get("bounding_box")
            if not isinstance(bbox, list) or len(bbox) != 4:
                continue
            label = f"RP detecte page {page} bbox={bbox}"
            if label not in points:
                points.append(label)
        result_json["points_pression_reduction"] = points[:20]

    if brise_dets:
        result_json["presence_brise_charge"] = True
        existing = result_json.get("nombre_brise_charge")
        brise_count = len(brise_dets)
        if isinstance(existing, (int, float)):
            result_json["nombre_brise_charge"] = max(int(existing), brise_count)
        else:
            result_json["nombre_brise_charge"] = brise_count
