from __future__ import annotations

import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional

import anyio
import httpx
import structlog

from .config import Settings
from .models import OpenRouterResponse


logger = structlog.get_logger(__name__)


class RouterClientError(Exception):
    """Base exception for RouterClient errors."""


class RateLimitError(RouterClientError):
    """Raised when the API responds with HTTP 429."""


class ServerError(RouterClientError):
    """Raised when the API responds with HTTP 5xx beyond retry budget."""


class ParseError(RouterClientError):
    """Raised when the JSON payload could not be parsed."""


class ConnectionError(RouterClientError):
    """Raised when network connectivity fails for too long."""


class BudgetExceededError(RouterClientError):
    """Raised when the configured budget would be exceeded."""


class RouterClient:
    """Thin asynchronous wrapper around the OpenRouter chat API."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        timeout = httpx.Timeout(
            connect=settings.http.timeout_connect,
            read=settings.http.timeout_read,
            write=settings.http.timeout_write,
            pool=settings.http.timeout_pool,
        )
        headers = {
            "Authorization": f"Bearer {settings.openrouter_api_key}",
        }
        self._client = httpx.AsyncClient(
            base_url=settings.http.base_url, timeout=timeout, headers=headers
        )
        self._model_semaphores: Dict[str, anyio.Semaphore] = defaultdict(
            lambda: anyio.Semaphore(settings.rate_limit.per_model_concurrency)
        )
        self._global_window: Deque[float] = deque()
        self._global_limit = settings.rate_limit.global_requests_per_minute
        self._cumulative_cost = 0.0
        self._window_lock = anyio.Lock()
        self._budget_lock = anyio.Lock()

    async def close(self) -> None:
        await self._client.aclose()

    @property
    def cumulative_cost_usd(self) -> float:
        return self._cumulative_cost

    async def _respect_global_rate_limit(self) -> None:
        while True:
            async with self._window_lock:
                now = time.monotonic()
                cutoff = now - 60.0
                while self._global_window and self._global_window[0] < cutoff:
                    self._global_window.popleft()
                if len(self._global_window) < self._global_limit:
                    self._global_window.append(now)
                    return
                sleep_for = self._global_window[0] + 60.0 - now
            await anyio.sleep(max(sleep_for, 0.0))

    def _price_for_model(self, model: str) -> Optional[float]:
        return self._settings.price_overrides.get(model)

    async def _calculate_cost(
        self, model: str, response: httpx.Response, prompt_tokens: int, completion_tokens: int
    ) -> float:
        header_price = response.headers.get("x-openrouter-price")
        if header_price:
            try:
                return (prompt_tokens + completion_tokens) / 1000.0 * float(header_price)
            except ValueError:
                logger.warning("failed_to_parse_price_header", header_value=header_price)
        override = self._price_for_model(model)
        if override is not None:
            return (prompt_tokens + completion_tokens) / 1000.0 * override
        return 0.0

    async def chat(self, *, model: str, prompt: str, temperature: float) -> OpenRouterResponse:
        async with self._budget_lock:
            if self._cumulative_cost >= self._settings.budget.max_budget_usd:
                raise BudgetExceededError("Budget exhausted")

        async with self._model_semaphores[model]:
            await self._respect_global_rate_limit()
            payload = {
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "temperature": temperature,
            }

            if model.lower().startswith("openai/o"):
                payload.setdefault("include_reasoning", False)
                payload.setdefault("reasoning", {"effort": "low"})

            max_attempts = 10
            rate_limit_attempts = 0
            server_attempts = 0
            connection_started_at: Optional[float] = None

            for attempt in range(1, max_attempts + 1):
                try:
                    response = await self._client.post("/chat/completions", json=payload)
                except httpx.RequestError as exc:
                    now = time.monotonic()
                    connection_started_at = connection_started_at or now
                    if now - connection_started_at > 30.0:
                        raise ConnectionError("connection retry budget exhausted") from exc
                    await anyio.sleep(2.0)
                    continue

                if response.status_code == 429:
                    rate_limit_attempts += 1
                    if rate_limit_attempts > 5:
                        raise RateLimitError("rate limit retries exhausted")
                    retry_after = response.headers.get("Retry-After")
                    try:
                        delay = float(retry_after) if retry_after else 2.0 ** rate_limit_attempts
                    except ValueError:
                        delay = 2.0 ** rate_limit_attempts
                    await anyio.sleep(min(delay, 60.0))
                    continue

                if 500 <= response.status_code < 600:
                    server_attempts += 1
                    if server_attempts > 3:
                        raise ServerError(f"server error {response.status_code}")
                    await anyio.sleep(5.0 * server_attempts)
                    continue

                if response.is_error:
                    raise RouterClientError(
                        f"http error {response.status_code}: {response.text[:200]}"
                    )

                try:
                    data = response.json()
                except ValueError as exc:  # pragma: no cover - invalid JSON is rare
                    raise ParseError("invalid JSON") from exc

                choices = data.get("choices")
                if not choices:
                    raise ParseError("missing choices")
                message = choices[0].get("message", {})
                text = message.get("content")
                if text is None:
                    raise ParseError("missing content")

                usage = data.get("usage", {})
                prompt_tokens = int(usage.get("prompt_tokens", 0))
                completion_tokens = int(usage.get("completion_tokens", 0))
                cost = await self._calculate_cost(model, response, prompt_tokens, completion_tokens)

                max_budget = self._settings.budget.max_budget_usd
                warn_fraction = self._settings.budget.warn_at_fraction

                async with self._budget_lock:
                    self._cumulative_cost += cost
                    cumulative_cost = self._cumulative_cost
                    exceeded_budget = cumulative_cost > max_budget
                    warn_threshold = cumulative_cost > max_budget * warn_fraction

                if exceeded_budget:
                    logger.warning(
                        "budget_threshold_crossed", cumulative_cost=cumulative_cost
                    )
                    raise BudgetExceededError("Budget exhausted")

                if warn_threshold:
                    logger.info("budget_warning", cumulative_cost=cumulative_cost)

                return OpenRouterResponse(
                    text=text,
                    prompt_tokens=prompt_tokens,
                    completion_tokens=completion_tokens,
                    status_code=response.status_code,
                    cost_usd=cost,
                )

            raise RouterClientError("exhausted retries")
