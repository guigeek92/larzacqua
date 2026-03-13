from __future__ import annotations

import uuid
from pathlib import Path

from src.run_history_store import RunHistoryStore


def _build_run(run_id: str, value: int) -> dict:
    return {
        "run_id": run_id,
        "timestamp": "2026-03-10 10:00:00",
        "model": "llama-3.1-8b-instant",
        "total_files": 1,
        "success_count": 1,
        "error_count": 0,
        "results": [{"site_name": "Site A", "result_json": {"debit_m3_j": value}}],
        "errors": [],
    }


def test_upsert_and_list_runs(tmp_path: Path) -> None:
    store = RunHistoryStore(tmp_path / "history.sqlite3")
    run_a = _build_run(uuid.uuid4().hex, 12)
    run_b = _build_run(uuid.uuid4().hex, 42)

    store.upsert_run(run_a)
    store.upsert_run(run_b)

    runs = store.list_runs(limit=10)

    assert len(runs) == 2
    run_ids = {run["run_id"] for run in runs}
    assert run_a["run_id"] in run_ids
    assert run_b["run_id"] in run_ids


def test_update_existing_run_payload(tmp_path: Path) -> None:
    store = RunHistoryStore(tmp_path / "history.sqlite3")
    run_id = uuid.uuid4().hex
    run = _build_run(run_id, 15)
    store.upsert_run(run)

    run["results"][0]["result_json"]["debit_m3_j"] = 99
    run["results"][0]["result_json"]["hauteur_chute_estimee_m"] = 28
    store.upsert_run(run)

    saved = [item for item in store.list_runs(limit=5) if item.get("run_id") == run_id][0]
    result_json = saved["results"][0]["result_json"]
    assert result_json["debit_m3_j"] == 99
    assert result_json["hauteur_chute_estimee_m"] == 28


def test_clear_history(tmp_path: Path) -> None:
    store = RunHistoryStore(tmp_path / "history.sqlite3")
    store.upsert_run(_build_run(uuid.uuid4().hex, 1))

    store.clear()

    assert store.list_runs(limit=5) == []
