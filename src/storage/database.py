from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any, Dict, List

import structlog

from ..config import Settings
from ..models import BenchmarkRecord


logger = structlog.get_logger(__name__)


RECORDS_DDL = """
CREATE TABLE IF NOT EXISTS records (
  id TEXT PRIMARY KEY,
  run_id TEXT,
  model TEXT,
  run INTEGER,
  gewuenscht TEXT,
  bekommen TEXT,
  phonetische_aehnlichkeit INTEGER,
  anzueglichkeit INTEGER,
  logik INTEGER,
  kreativitaet INTEGER,
  gesamt INTEGER,
  prompt_tokens INTEGER,
  completion_tokens INTEGER,
  cost_usd REAL,
  ts TEXT
);
"""

INDEX_DDL = "CREATE INDEX IF NOT EXISTS idx_records_model ON records(model);"


def _database_path(settings: Settings, run_id: str) -> Path:
    base = settings.resolved_base_path() / run_id
    base.mkdir(parents=True, exist_ok=True)
    filename = settings.storage.sqlite_filename_template.format(run_id=run_id)
    return base / filename


def connect(settings: Settings, run_id: str) -> sqlite3.Connection:
    path = _database_path(settings, run_id)
    conn = sqlite3.connect(path, detect_types=sqlite3.PARSE_DECLTYPES)
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    with conn:
        conn.executescript(RECORDS_DDL)
        conn.execute(INDEX_DDL)


def upsert_record(conn: sqlite3.Connection, run_id: str, record: BenchmarkRecord) -> None:
    payload = (
        f"{run_id}_{record.generation.model}_{record.generation.run}",
        run_id,
        record.generation.model,
        record.generation.run,
        record.generation.summary.gewuenscht,
        record.generation.summary.bekommen,
        record.judge.phonetische_aehnlichkeit,
        record.judge.anzueglichkeit,
        record.judge.logik,
        record.judge.kreativitaet,
        record.judge.gesamt,
        record.generation.prompt_tokens,
        record.generation.completion_tokens,
        record.generation.cost_usd,
        record.generation.timestamp.isoformat(),
    )
    with conn:
        conn.execute(
            """
            INSERT INTO records (
                id, run_id, model, run, gewuenscht, bekommen,
                phonetische_aehnlichkeit, anzueglichkeit, logik, kreativitaet, gesamt,
                prompt_tokens, completion_tokens, cost_usd, ts
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                phonetische_aehnlichkeit=excluded.phonetische_aehnlichkeit,
                anzueglichkeit=excluded.anzueglichkeit,
                logik=excluded.logik,
                kreativitaet=excluded.kreativitaet,
                gesamt=excluded.gesamt,
                prompt_tokens=excluded.prompt_tokens,
                completion_tokens=excluded.completion_tokens,
                cost_usd=excluded.cost_usd,
                ts=excluded.ts
            """,
            payload,
        )


def fetch_records_for_model(conn: sqlite3.Connection, model: str) -> List[Dict[str, Any]]:
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT * FROM records WHERE model = ?", (model,)).fetchall()
    return [dict(row) for row in rows]


__all__ = ["connect", "ensure_schema", "upsert_record", "fetch_records_for_model"]
