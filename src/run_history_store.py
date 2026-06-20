from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any


def _normalize_filename(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return Path(text).name.strip().lower()


def compute_run_signature(run_record: dict[str, Any]) -> str:
    filenames: set[str] = set()

    for entry in run_record.get("results", []) or []:
        if isinstance(entry, dict):
            normalized = _normalize_filename(entry.get("filename"))
            if normalized:
                filenames.add(normalized)

    for entry in run_record.get("errors", []) or []:
        if isinstance(entry, dict):
            normalized = _normalize_filename(entry.get("filename"))
            if normalized:
                filenames.add(normalized)

    if not filenames:
        return ""

    signature_payload = "\n".join(sorted(filenames))
    return hashlib.sha1(signature_payload.encode("utf-8")).hexdigest()


class RunHistoryStore:
    """SQLite-backed persistent store for analysis runs."""

    def __init__(self, db_path: Path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize_schema()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_runs_updated_at ON runs(updated_at DESC)")

    def upsert_run(self, run_record: dict[str, Any]) -> str:
        run_id = str(run_record.get("run_id") or "").strip()
        if not run_id:
            raise ValueError("run_record must include a non-empty run_id")

        now_iso = datetime.utcnow().isoformat(timespec="microseconds")
        payload = json.dumps(run_record, ensure_ascii=False)

        with self._connect() as conn:
            existing = conn.execute("SELECT created_at FROM runs WHERE run_id = ?", (run_id,)).fetchone()
            created_at = existing["created_at"] if existing else now_iso
            conn.execute(
                """
                INSERT INTO runs (run_id, created_at, updated_at, payload_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(run_id) DO UPDATE SET
                    updated_at = excluded.updated_at,
                    payload_json = excluded.payload_json
                """,
                (run_id, created_at, now_iso, payload),
            )

        return run_id

    def list_runs(self, limit: int = 30) -> list[dict[str, Any]]:
        query = "SELECT payload_json FROM runs ORDER BY updated_at DESC"
        params: tuple[Any, ...] = ()
        if limit > 0:
            query += " LIMIT ?"
            params = (int(limit),)

        with self._connect() as conn:
            rows = conn.execute(query, params).fetchall()

        runs: list[dict[str, Any]] = []
        seen_signatures: set[str] = set()
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
                if isinstance(payload, dict):
                    signature = compute_run_signature(payload)
                    if signature:
                        if signature in seen_signatures:
                            continue
                        seen_signatures.add(signature)
                    runs.append(payload)
            except json.JSONDecodeError:
                continue
        return runs

    def find_run_by_signature(self, signature: str) -> dict[str, Any] | None:
        normalized_signature = str(signature or "").strip()
        if not normalized_signature:
            return None

        for run in self.list_runs(limit=0):
            if compute_run_signature(run) == normalized_signature:
                return run
        return None

    def clear(self) -> None:
        with self._connect() as conn:
            conn.execute("DELETE FROM runs")
