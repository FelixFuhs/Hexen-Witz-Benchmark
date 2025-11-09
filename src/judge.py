from __future__ import annotations

import json
import re
from pathlib import Path

import structlog

from .config import Settings
from .models import BenchmarkRecord, GenerationResult, JudgeScore
from .router_client import RouterClient
from .storage import files


logger = structlog.get_logger(__name__)


SCORE_BOUNDS = {
    "phonetische_aehnlichkeit": (0, 35),
    "anzueglichkeit": (0, 25),
    "logik": (0, 20),
    "kreativitaet": (0, 20),
    "gesamt": (0, 100),
}


def load_judge_prompt(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"judge prompt template missing at {path}")
    return path.read_text(encoding="utf-8")


def format_judge_prompt(template: str, generation: GenerationResult) -> str:
    prompt = template.replace(
        "[Was sich der Gast von der Hexe wünscht – wird hier automatisch eingefügt]",
        generation.summary.gewuenscht,
    )
    prompt = prompt.replace(
        "[Was er stattdessen bekommt – wird hier automatisch eingefügt]",
        generation.summary.bekommen,
    )
    prompt = prompt.replace(
        "[VOLLSTAENDIGE ANTWORT DES GETESTETEN MODELLS: hier die komplette Antwort des LLMs einfügen]",
        generation.full_response,
    )
    return prompt


def _extract_json_block(text: str) -> str:
    match = re.search(r"```(?:json)?\s*([\s\S]+?)```", text, flags=re.IGNORECASE)
    return match.group(1) if match else text


def _clamp_scores(payload: dict) -> dict:
    flags = payload.setdefault("flags", [])
    for key, (lower, upper) in SCORE_BOUNDS.items():
        value = payload.get(key)
        if value is None:
            continue
        try:
            numeric = int(value)
        except (TypeError, ValueError):
            raise ValueError(f"score '{key}' is not an integer")
        if numeric < lower:
            payload[key] = lower
            flags.append(f"{key}_clamped_min")
        elif numeric > upper:
            payload[key] = upper
            flags.append(f"{key}_clamped_max")
        else:
            payload[key] = numeric
    return payload


async def judge_generation(
    *,
    client: RouterClient,
    generation: GenerationResult,
    judge_model: str,
    template: str,
    temperature: float = 0.0,
) -> JudgeScore:
    prompt = format_judge_prompt(template, generation)
    response = await client.chat(model=judge_model, prompt=prompt, temperature=temperature)
    json_payload = _extract_json_block(response["text"])
    try:
        parsed = json.loads(json_payload)
    except json.JSONDecodeError as exc:
        logger.error("judge_json_decode_failed", error=str(exc), payload=response["text"][:200])
        raise
    clamped = _clamp_scores(parsed)
    if "begruendung" not in clamped:
        raise ValueError("judge response missing begruendung")
    score = JudgeScore(**clamped)
    return score


async def judge_and_store(
    *,
    client: RouterClient,
    generation: GenerationResult,
    judge_model: str,
    template: str,
    run_id: str,
    settings: Settings,
) -> BenchmarkRecord:
    score = await judge_generation(
        client=client,
        generation=generation,
        judge_model=judge_model,
        template=template,
    )
    record = BenchmarkRecord(generation=generation, judge=score)
    files.save_benchmark_record(record=record, run_id=run_id, settings=settings)
    return record


__all__ = ["judge_generation", "judge_and_store", "format_judge_prompt", "load_judge_prompt"]
