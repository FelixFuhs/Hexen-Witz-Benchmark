from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, Optional

import pandas as pd
import structlog
import typer

from .config import Settings
from .judge import judge_and_store, load_judge_prompt
from .main import run_sync
from .models import GenerationResult
from .router_client import RouterClient
from .storage import database


app = typer.Typer(help="Schwerhörige-Hexe Benchmark CLI")


def configure_logging(level: str) -> None:
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=numeric)
    structlog.configure(
        wrapper_class=structlog.make_filtering_bound_logger(numeric),
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.KeyValueRenderer(sort_keys=True),
        ],
    )
    structlog.get_logger().bind(log_level=level.upper())


@app.command()
def run(
    model: Optional[Iterable[str]] = typer.Option(None, "--model", "-m"),
    iterations: int = typer.Option(1, "--iterations", "-n", min=1),
    run_id: Optional[str] = typer.Option(None, "--run-id"),
    config: Optional[Path] = typer.Option(None, "--config", exists=True, dir_okay=False),
    log_level: str = typer.Option("info", "--log-level"),
) -> None:
    configure_logging(log_level.upper())
    settings = Settings(_env_file=str(config)) if config else Settings()
    run_sync(settings=settings, run_id=run_id, model_names=model, iterations=iterations)


@app.command()
def resume(
    run_id: str = typer.Argument(..., help="Run identifier to resume"),
    config: Optional[Path] = typer.Option(None, "--config", exists=True, dir_okay=False),
    log_level: str = typer.Option("info", "--log-level"),
) -> None:
    configure_logging(log_level.upper())
    settings = Settings(_env_file=str(config)) if config else Settings()
    run_path = settings.resolved_base_path() / run_id
    raw_dir = run_path / "raw"
    judged_dir = run_path / "judged"
    if not raw_dir.exists():
        raise typer.BadParameter(f"no raw results found for run {run_id}")
    client = RouterClient(settings)
    template = load_judge_prompt(Path("src/prompts/judge_checklist.md"))
    try:
        for raw_file in sorted(raw_dir.glob("*.json")):
            judged_file = judged_dir / raw_file.name
            if judged_file.exists():
                continue
            payload = json.loads(raw_file.read_text(encoding="utf-8"))
            generation = GenerationResult.model_validate(payload)
            judge_and_store_kwargs = dict(
                client=client,
                generation=generation,
                judge_model=settings.judge_model_name,
                template=template,
                run_id=run_id,
                settings=settings,
            )
            typer.echo(f"Judging {generation.model} run {generation.run} ...")
            # run async call
            from anyio import run as anyio_run

            anyio_run(judge_and_store, **judge_and_store_kwargs)
    finally:
        from anyio import run as anyio_run

        anyio_run(client.close)


@app.command()
def stats(
    run_id: str = typer.Argument(..., help="Run identifier to inspect"),
    config: Optional[Path] = typer.Option(None, "--config", exists=True, dir_okay=False),
) -> None:
    settings = Settings(_env_file=str(config)) if config else Settings()
    run_path = settings.resolved_base_path() / run_id
    parquet_path = run_path / settings.storage.parquet_filename
    if not parquet_path.exists():
        typer.echo("No parquet file found; attempting to read from SQLite")
        conn = database.connect(settings, run_id)
        try:
            database.ensure_schema(conn)
            rows = conn.execute("SELECT * FROM records").fetchall()
            df = pd.DataFrame([dict(row) for row in rows])
        finally:
            conn.close()
    else:
        df = pd.read_parquet(parquet_path)
    if df.empty:
        typer.echo("No records available for this run")
        return
    summary = df.groupby("model")["gesamt"].agg(["count", "mean", "min", "max"]).reset_index()
    typer.echo(summary.to_string(index=False))


if __name__ == "__main__":
    app()
