from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from src.models import BenchmarkRecord, GenerationResult, JudgeScore, Summary


def test_generation_result_requires_summary() -> None:
    summary = Summary(gewuenscht="Test", bekommen="Antwort")
    result = GenerationResult(
        model="model/a",
        run=1,
        summary=summary,
        full_response="response",
        prompt_tokens=10,
        completion_tokens=5,
        cost_usd=0.02,
        timestamp=datetime.now(timezone.utc),
    )
    assert result.summary == summary


def test_generation_result_missing_summary_raises() -> None:
    with pytest.raises(ValidationError):
        GenerationResult(
            model="model/a",
            run=1,
            summary=None,  # type: ignore[arg-type]
            full_response="response",
            prompt_tokens=1,
            completion_tokens=1,
            cost_usd=0.0,
            timestamp=datetime.now(timezone.utc),
        )


def test_judge_score_bounds_enforced() -> None:
    with pytest.raises(ValidationError):
        JudgeScore(
            phonetische_aehnlichkeit=40,
            anzueglichkeit=10,
            logik=10,
            kreativitaet=10,
            gesamt=50,
            begruendung={"test": "value"},
        )


def test_benchmark_record_combines_generation_and_judge() -> None:
    summary = Summary(gewuenscht="Test", bekommen="Antwort")
    generation = GenerationResult(
        model="model/a",
        run=2,
        summary=summary,
        full_response="response",
        prompt_tokens=12,
        completion_tokens=6,
        cost_usd=0.03,
        timestamp=datetime.now(timezone.utc),
    )
    judge = JudgeScore(
        phonetische_aehnlichkeit=30,
        anzueglichkeit=10,
        logik=10,
        kreativitaet=10,
        gesamt=60,
        begruendung={"gesamt": "ok"},
    )
    record = BenchmarkRecord(generation=generation, judge=judge)
    assert record.generation.model == "model/a"
    assert record.judge.gesamt == 60
