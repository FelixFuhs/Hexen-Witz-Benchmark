from __future__ import annotations

import csv
import json
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import boto3
import pandas as pd
import structlog

from ..config import Settings
from ..models import BenchmarkRecord, GenerationResult
from . import database


logger = structlog.get_logger(__name__)


def _run_path(settings: Settings, run_id: str) -> Path:
    base = settings.resolved_base_path()
    run_path = base / run_id
    (run_path / "raw").mkdir(parents=True, exist_ok=True)
    (run_path / "judged").mkdir(parents=True, exist_ok=True)
    return run_path


def _safe_model_filename(model: str, run_number: int) -> str:
    safe_model = model.replace("/", "_").replace(":", "_")
    return f"{safe_model}_{run_number}.json"


def _update_cost_report(settings: Settings, run_id: str, result: GenerationResult) -> None:
    run_path = _run_path(settings, run_id)
    cost_path = run_path / "cost_report.csv"
    file_exists = cost_path.exists()
    with cost_path.open("a", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        if not file_exists:
            writer.writerow(
                [
                    "timestamp",
                    "run_id",
                    "model",
                    "run",
                    "cost_usd",
                    "prompt_tokens",
                    "completion_tokens",
                ]
            )
        writer.writerow(
            [
                result.timestamp.isoformat(),
                run_id,
                result.model,
                result.run,
                f"{result.cost_usd:.8f}",
                result.prompt_tokens,
                result.completion_tokens,
            ]
        )


def _parquet_path(settings: Settings, run_id: str) -> Path:
    return _run_path(settings, run_id) / settings.storage.parquet_filename


def _update_parquet(settings: Settings, run_id: str, record: BenchmarkRecord) -> None:
    path = _parquet_path(settings, run_id)
    df = pd.DataFrame(
        [
            {
                "run_id": run_id,
                "model": record.generation.model,
                "run": record.generation.run,
                "gewuenscht": record.generation.summary.gewuenscht,
                "bekommen": record.generation.summary.bekommen,
                "phonetische_aehnlichkeit": record.judge.phonetische_aehnlichkeit,
                "anzueglichkeit": record.judge.anzueglichkeit,
                "logik": record.judge.logik,
                "kreativitaet": record.judge.kreativitaet,
                "gesamt": record.judge.gesamt,
                "prompt_tokens": record.generation.prompt_tokens,
                "completion_tokens": record.generation.completion_tokens,
                "cost_usd": record.generation.cost_usd,
                "timestamp": record.generation.timestamp,
            }
        ]
    )
    if path.exists():
        existing = pd.read_parquet(path)
        df = pd.concat([existing, df], ignore_index=True)
    df.to_parquet(path, index=False)


def _upload_to_s3(settings: Settings, run_id: str, path: Path) -> None:
    if not settings.storage.enable_s3 or not settings.storage.s3_bucket:
        return
    client = boto3.client("s3")
    key = f"{settings.storage.s3_prefix}{run_id}/{path.name}"
    client.upload_file(str(path), settings.storage.s3_bucket, key)
    logger.info("uploaded_to_s3", bucket=settings.storage.s3_bucket, key=key)


def save_generation_result(*, result: GenerationResult, run_id: str, settings: Settings) -> Path:
    run_path = _run_path(settings, run_id)
    file_path = run_path / "raw" / _safe_model_filename(result.model, result.run)
    file_path.write_text(result.model_dump_json(indent=2), encoding="utf-8")
    checksum = hashlib.sha256(file_path.read_bytes()).hexdigest()
    logger.info("generation_saved", path=str(file_path), checksum=checksum)
    _update_cost_report(settings, run_id, result)
    _upload_to_s3(settings, run_id, file_path)
    return file_path


def save_benchmark_record(*, record: BenchmarkRecord, run_id: str, settings: Settings) -> Path:
    run_path = _run_path(settings, run_id)
    file_path = run_path / "judged" / _safe_model_filename(record.generation.model, record.generation.run)
    file_path.write_text(record.model_dump_json(indent=2), encoding="utf-8")
    checksum = hashlib.sha256(file_path.read_bytes()).hexdigest()
    logger.info("benchmark_saved", path=str(file_path), checksum=checksum)
    _update_parquet(settings, run_id, record)
    conn = database.connect(settings, run_id)
    try:
        database.ensure_schema(conn)
        database.upsert_record(conn, run_id, record)
    finally:
        conn.close()
    _upload_to_s3(settings, run_id, file_path)
    _upload_to_s3(settings, run_id, _parquet_path(settings, run_id))
    return file_path


def write_meta_json(*, run_id: str, settings: Settings) -> Path:
    run_path = _run_path(settings, run_id)
    meta_path = run_path / "meta.json"
    config_payload = settings.model_dump(mode="json", exclude={"openrouter_api_key"})
    payload: dict[str, Any] = {
        "run_id": run_id,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "config": config_payload,
    }
    meta_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    _upload_to_s3(settings, run_id, meta_path)
    return meta_path


__all__ = ["save_generation_result", "save_benchmark_record", "write_meta_json"]
