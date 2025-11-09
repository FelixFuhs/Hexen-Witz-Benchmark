from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, List

import structlog

from .config import ModelConfig, Settings
from .extractor import SummaryParseError, extract_summary
from .models import GenerationResult, Summary
from .router_client import RouterClient
from .storage import files


logger = structlog.get_logger(__name__)


def load_benchmark_prompt(prompt_path: Path) -> str:
    if not prompt_path.exists():
        raise FileNotFoundError(f"prompt file missing at {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


def _fallback_summary(reason: str) -> Summary:
    logger.warning("summary_fallback", reason=reason)
    return Summary(gewuenscht="(kein Eintrag)", bekommen="(kein Eintrag)")


async def generate_joke(
    client: RouterClient,
    model: ModelConfig,
    prompt: str,
    run_number: int,
) -> GenerationResult:
    response = await client.chat(model=model.name, prompt=prompt, temperature=model.temperature)

    try:
        summary = extract_summary(response["text"])
    except SummaryParseError as exc:
        summary = _fallback_summary(str(exc))

    timestamp = datetime.now(timezone.utc)
    return GenerationResult(
        model=model.name,
        run=run_number,
        summary=summary,
        full_response=response["text"],
        prompt_tokens=response["prompt_tokens"],
        completion_tokens=response["completion_tokens"],
        cost_usd=response["cost_usd"],
        timestamp=timestamp,
    )


async def run_model_generations(
    *,
    client: RouterClient,
    settings: Settings,
    model: ModelConfig,
    prompt: str,
    run_id: str,
    iterations: int,
) -> List[GenerationResult]:
    results: List[GenerationResult] = []
    for index in range(1, iterations + 1):
        result = await generate_joke(client, model, prompt, index)
        results.append(result)
        files.save_generation_result(result=result, run_id=run_id, settings=settings)
    return results


async def run_benchmark(
    *,
    client: RouterClient,
    settings: Settings,
    run_id: str,
    prompt_path: Path,
    iterations: int,
    models: Iterable[ModelConfig] | None = None,
) -> List[GenerationResult]:
    prompt = load_benchmark_prompt(prompt_path)
    all_results: List[GenerationResult] = []
    for model in models or settings.candidate_models:
        results = await run_model_generations(
            client=client,
            settings=settings,
            model=model,
            prompt=prompt,
            run_id=run_id,
            iterations=iterations,
        )
        all_results.extend(results)
    files.write_meta_json(run_id=run_id, settings=settings)
    return all_results


__all__ = ["generate_joke", "run_benchmark", "run_model_generations", "load_benchmark_prompt"]
