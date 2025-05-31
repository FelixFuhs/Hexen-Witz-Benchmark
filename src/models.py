from pydantic import BaseModel, Field
from typing import TypedDict, Dict
from datetime import datetime

class Summary(BaseModel):
    gewuenscht: str
    bekommen: str

class GenerationResult(BaseModel):
    model: str
    run: int
    summary: Summary
    full_response: str
    prompt_tokens: int
    completion_tokens: int
    timestamp: datetime

class JudgeScore(BaseModel):
    phonetische_aehnlichkeit: int = Field(ge=0, le=35)
    anzueglichkeit: int = Field(ge=0, le=25)
    logik: int = Field(ge=0, le=20)
    kreativitaet: int = Field(ge=0, le=20)
    gesamt: int = Field(ge=0, le=100)
    begruendung: Dict[str, str]

class BenchmarkRecord(BaseModel):
    generation: GenerationResult
    judge: JudgeScore

class OpenRouterResponse(TypedDict):
    text: str
    prompt_tokens: int
    completion_tokens: int
    status_code: int
    cost_usd: float
