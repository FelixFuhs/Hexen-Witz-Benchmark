from __future__ import annotations

from datetime import datetime
from typing import Dict, TypedDict

from pydantic import BaseModel, Field


class Summary(BaseModel):
    gewuenscht: str = Field(min_length=1)
    bekommen: str = Field(min_length=1)


class GenerationResult(BaseModel):
    model: str
    run: int = Field(ge=1)
    summary: Summary
    full_response: str
    prompt_tokens: int = Field(ge=0)
    completion_tokens: int = Field(ge=0)
    cost_usd: float = Field(ge=0.0)
    timestamp: datetime


class JudgeScore(BaseModel):
    phonetische_aehnlichkeit: int = Field(ge=0, le=35)
    anzueglichkeit: int = Field(ge=0, le=25)
    logik: int = Field(ge=0, le=20)
    kreativitaet: int = Field(ge=0, le=20)
    gesamt: int = Field(ge=0, le=100)
    begruendung: Dict[str, str]
    flags: list[str] = Field(default_factory=list)


class BenchmarkRecord(BaseModel):
    generation: GenerationResult
    judge: JudgeScore


class OpenRouterResponse(TypedDict):
    text: str
    prompt_tokens: int
    completion_tokens: int
    status_code: int
    cost_usd: float
