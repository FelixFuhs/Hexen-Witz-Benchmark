from pydantic import BaseModel, Field, field_validator, ValidationInfo
from typing import TypedDict, Dict, Optional, List
from datetime import datetime

class Summary(BaseModel):
    gewuenscht: str
    bekommen: str

class GenerationResult(BaseModel):
    model: str
    run: int
    summary: Optional[Summary] = None
    full_response: str
    prompt_tokens: int
    completion_tokens: int
    cost_usd: float # Cost of this specific generation call
    timestamp: datetime

class JudgeScore(BaseModel):
    phonetische_aehnlichkeit: int = Field(default=0)
    anzueglichkeit: int = Field(default=0)
    logik: int = Field(default=0)
    kreativitaet: int = Field(default=0)
    gesamt: int = Field(default=0) # This could also be calculated
    begruendung: Dict[str, str]
    flags: List[str] = Field(default_factory=list)

    @field_validator('phonetische_aehnlichkeit')
    @classmethod
    def clamp_phonetische_aehnlichkeit(cls, v: int, info: ValidationInfo) -> int:
        field_name = 'phonetische_aehnlichkeit'
        min_val, max_val = 0, 35
        if v < min_val:
            if info.data is not None and 'flags' in info.data:
                 info.data['flags'].append(f"{field_name}_clamped_min_to_{min_val}")
            return min_val
        if v > max_val:
            if info.data is not None and 'flags' in info.data:
                info.data['flags'].append(f"{field_name}_clamped_max_to_{max_val}")
            return max_val
        return v

    @field_validator('anzueglichkeit')
    @classmethod
    def clamp_anzueglichkeit(cls, v: int, info: ValidationInfo) -> int:
        field_name = 'anzueglichkeit'
        min_val, max_val = 0, 25
        if v < min_val:
            if info.data is not None and 'flags' in info.data:
                 info.data['flags'].append(f"{field_name}_clamped_min_to_{min_val}")
            return min_val
        if v > max_val:
            if info.data is not None and 'flags' in info.data:
                info.data['flags'].append(f"{field_name}_clamped_max_to_{max_val}")
            return max_val
        return v

    @field_validator('logik')
    @classmethod
    def clamp_logik(cls, v: int, info: ValidationInfo) -> int:
        field_name = 'logik'
        min_val, max_val = 0, 20
        if v < min_val:
            if info.data is not None and 'flags' in info.data:
                 info.data['flags'].append(f"{field_name}_clamped_min_to_{min_val}")
            return min_val
        if v > max_val:
            if info.data is not None and 'flags' in info.data:
                info.data['flags'].append(f"{field_name}_clamped_max_to_{max_val}")
            return max_val
        return v

    @field_validator('kreativitaet')
    @classmethod
    def clamp_kreativitaet(cls, v: int, info: ValidationInfo) -> int:
        field_name = 'kreativitaet'
        min_val, max_val = 0, 20
        if v < min_val:
            if info.data is not None and 'flags' in info.data:
                 info.data['flags'].append(f"{field_name}_clamped_min_to_{min_val}")
            return min_val
        if v > max_val:
            if info.data is not None and 'flags' in info.data:
                info.data['flags'].append(f"{field_name}_clamped_max_to_{max_val}")
            return max_val
        return v

    @field_validator('gesamt')
    @classmethod
    def clamp_gesamt(cls, v: int, info: ValidationInfo) -> int:
        # Optionally, gesamt could be a sum of other scores, validated separately.
        # For now, it's an independent, clampable field.
        field_name = 'gesamt'
        min_val, max_val = 0, 100
        if v < min_val:
            if info.data is not None and 'flags' in info.data:
                 info.data['flags'].append(f"{field_name}_clamped_min_to_{min_val}")
            return min_val
        if v > max_val:
            if info.data is not None and 'flags' in info.data:
                info.data['flags'].append(f"{field_name}_clamped_max_to_{max_val}")
            return max_val
        return v

class BenchmarkRecord(BaseModel):
    generation: GenerationResult
    judge: JudgeScore

class OpenRouterResponse(TypedDict):
    text: str
    prompt_tokens: int
    completion_tokens: int
    status_code: int
    cost_usd: float
