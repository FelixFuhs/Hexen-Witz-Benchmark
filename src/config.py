from __future__ import annotations

from pathlib import Path
from typing import Dict, List, Optional

from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class ModelConfig(BaseModel):
    """Configuration for a single candidate model."""

    name: str
    temperature: float = Field(default=0.8, ge=0.0, le=2.0)
    top_p: float = Field(default=0.9, ge=0.0, le=1.0)
    max_tokens: Optional[int] = Field(default=None, ge=1)
    metadata: Dict[str, str] = Field(default_factory=dict)


class StorageConfig(BaseModel):
    """Paths and toggles for file based artefacts and optional S3 backups."""

    base_path: Path = Field(default=Path("benchmarks"))
    enable_s3: bool = False
    s3_bucket: Optional[str] = None
    s3_prefix: str = "hexe-bench/"
    parquet_filename: str = "combined.parquet"
    sqlite_filename_template: str = "{run_id}_benchmark_data.sqlite"


class BudgetConfig(BaseModel):
    max_budget_usd: float = Field(default=100.0, ge=0.0)
    warn_at_fraction: float = Field(default=0.9, ge=0.0, le=1.0)


class RateLimitConfig(BaseModel):
    per_model_concurrency: int = Field(default=2, ge=1)
    global_requests_per_minute: int = Field(default=60, ge=1)


class HttpConfig(BaseModel):
    base_url: str = "https://openrouter.ai/api/v1"
    timeout_connect: float = Field(default=5.0, ge=0.1)
    timeout_read: float = Field(default=90.0, ge=1.0)
    timeout_write: float = Field(default=90.0, ge=1.0)
    timeout_pool: float = Field(default=5.0, ge=0.1)


class Settings(BaseSettings):
    """Global application configuration loaded from environment / .env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    openrouter_api_key: str = Field(alias="OPENROUTER_API_KEY")
    run_name: str = Field(default="local-run")
    judge_model_name: str = Field(default="openai/gpt-4o", alias="JUDGE_MODEL_NAME")
    candidate_models: List[ModelConfig] = Field(
        default_factory=lambda: [
            ModelConfig(name="mistralai/mistral-7b-instruct", temperature=0.8),
            ModelConfig(name="openai/gpt-4o-mini", temperature=0.6),
        ]
    )
    storage: StorageConfig = Field(default_factory=StorageConfig)
    budget: BudgetConfig = Field(default_factory=BudgetConfig)
    rate_limit: RateLimitConfig = Field(default_factory=RateLimitConfig)
    http: HttpConfig = Field(default_factory=HttpConfig)
    price_overrides: Dict[str, float] = Field(default_factory=dict)

    def resolved_base_path(self) -> Path:
        base = self.storage.base_path
        base.mkdir(parents=True, exist_ok=True)
        return base


__all__ = [
    "BudgetConfig",
    "HttpConfig",
    "ModelConfig",
    "RateLimitConfig",
    "Settings",
    "StorageConfig",
]
