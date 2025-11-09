from __future__ import annotations

import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List, Optional

import structlog

from .config import ModelConfig, Settings
from .generator import run_benchmark as run_generation_phase
from .judge import judge_and_store, load_judge_prompt
from .models import BenchmarkRecord, GenerationResult
from .router_client import BudgetExceededError, RouterClient


logger = structlog.get_logger(__name__)


async def _filter_models(settings: Settings, names: Optional[Iterable[str]]) -> List[ModelConfig]:
    if not names:
        return list(settings.candidate_models)
    mapping = {cfg.name: cfg for cfg in settings.candidate_models}
    missing = [name for name in names if name not in mapping]
    if missing:
        raise ValueError(f"unknown models requested: {', '.join(missing)}")
    return [mapping[name] for name in names]


async def run_benchmark(
    *,
    settings: Optional[Settings] = None,
    run_id: Optional[str] = None,
    model_names: Optional[Iterable[str]] = None,
    iterations: int = 1,
    prompt_path: Optional[Path] = None,
    judge_prompt_path: Optional[Path] = None,
) -> List[BenchmarkRecord]:
    resolved_settings = settings or Settings()
    current_run_id = run_id or f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    prompt_path = prompt_path or Path("src/prompts/benchmark_prompt.md")
    judge_prompt_path = judge_prompt_path or Path("src/prompts/judge_checklist.md")

    logger.info("starting_run", run_id=current_run_id)

    models = await _filter_models(resolved_settings, model_names)

    client = RouterClient(resolved_settings)
    try:
        generations: List[GenerationResult] = await run_generation_phase(
            client=client,
            settings=resolved_settings,
            run_id=current_run_id,
            prompt_path=prompt_path,
            iterations=iterations,
            models=models,
        )
        template = load_judge_prompt(judge_prompt_path)
        records: List[BenchmarkRecord] = []
        for generation in generations:
            try:
                record = await judge_and_store(
                    client=client,
                    generation=generation,
                    judge_model=resolved_settings.judge_model_name,
                    template=template,
                    run_id=current_run_id,
                    settings=resolved_settings,
                )
                records.append(record)
            except BudgetExceededError:
                logger.error("budget_exceeded_during_judging", run_id=current_run_id)
                break
        return records
    finally:
        await client.close()


def run_sync(**kwargs) -> List[BenchmarkRecord]:
    return asyncio.run(run_benchmark(**kwargs))


__all__ = ["run_benchmark", "run_sync"]
