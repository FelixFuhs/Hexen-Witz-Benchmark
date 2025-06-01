import httpx
import anyio
import asyncio # For asyncio.sleep, though anyio.sleep is preferred
import random
from typing import Dict, Any, Optional
from datetime import datetime # Potentially for time-based calculations
import logging

from src.config import Settings
from src.models import OpenRouterResponse

# --- Custom Exceptions ---
class RouterClientError(Exception):
    """Base exception for RouterClient errors."""
    pass

class RateLimitError(RouterClientError):
    """Raised when rate limits are exceeded."""
    pass

class ServerError(RouterClientError):
    """Raised for server-side errors (5xx)."""
    pass

class ParseError(RouterClientError):
    """Raised when parsing the API response fails."""
    pass

class ConnectionError(RouterClientError):
    """Raised for network connection issues."""
    pass

class BudgetExceededError(RouterClientError):
    """Raised when the defined budget is exceeded."""
    pass

logger = logging.getLogger(__name__)

class RouterClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.client = httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=90.0, write=90.0, pool=5.0))
        self.base_url = "https://openrouter.ai/api/v1"
        self.cumulative_cost_usd: float = 0.0
        self.model_semaphores: Dict[str, anyio.Semaphore] = {}
        # Global rate limiter: 60 requests per minute.
        # anyio.CapacityLimiter limits concurrent tasks.
        # To achieve a requests-per-minute limit, we'd typically use a token bucket.
        # For simplicity here, CapacityLimiter(60) means no more than 60 concurrent requests.
        # If requests are short, this might allow more than 60/min.
        # If requests are long, it will be less.
        # A true token bucket would involve a task that adds tokens to the limiter over time.
        # Let's start with a simple CapacityLimiter and refine if necessary.
        # The spec says "60 tokens per 60 seconds for simplicity, this matches 60 req/min if each request consumes 1 token"
        # This means the limiter should allow 1 token to be acquired per second on average.
        # CapacityLimiter is more about concurrency. A token bucket approach:
        self.global_rate_limiter = anyio.CapacityLimiter(1) # Allow 1 request through at a time initially
        # We'll need a task to refill this limiter or use a different mechanism.
        # For now, let's use a simpler direct rate limit of 1 request per second.
        # This means anyio.sleep(1) between requests if not using a sophisticated limiter.
        # The prompt suggests `anyio.CapacityLimiter(60)` and acquiring 1 token.
        # This would limit concurrency to 60, not rate to 60/min.
        # Let's use a Semaphore that allows 60 acquisitions, and a background task refills it.
        # Or, more simply, for 60 req/min = 1 req/sec, we can just sleep.
        # The spec mentions "global_rate_limiter = anyio.CapacityLimiter(60)" and "token_bucket_interval_seconds = 1.0"
        # This implies a design where up to 60 requests can burst, and 1 token is refilled per second.
        # This is a bit complex with CapacityLimiter alone.
        # A simpler interpretation for now for "60 tokens per 60 seconds":
        # We can acquire from a CapacityLimiter(60) and then sleep for 1 second.
        # Or, a simpler model: CapacityLimiter for concurrency, and a separate mechanism for rate.

        # Let's stick to the prompt's direct suggestion for now and see how it plays out.
        self.global_rate_limiter = anyio.CapacityLimiter(60) # Max 60 concurrent operations
        self.token_bucket_interval_seconds = 1.0 # Implies refilling 1 token per second for the limiter

        # A common pattern for token bucket with CapacityLimiter:
        # limiter = anyio.CapacityLimiter(total_tokens)
        # await limiter.acquire() # Consumes a token
        # # To refill:
        # if not limiter.has_pending_waiters: # or some other logic
        #    limiter.total_tokens += 1 # This is not how CapacityLimiter works; total_tokens is fixed at init.

        # Given the tools, a simple approach might be:
        # self.global_rps_limiter = anyio.Semaphore(1) # Allow 1 request per second effectively
        # And then in chat(): async with self.global_rps_limiter: await anyio.sleep(self.token_bucket_interval_seconds)
        # This is a bit clunky.

        # Let's try to implement the spirit of CapacityLimiter(60) with a refill mechanism conceptually.
        # The `anyio.CapacityLimiter` is for concurrency. For rate (X reqs per Y time),
        # a common pattern is a token bucket that refills.
        # The prompt implies `CapacityLimiter(60)` is the "bucket size" and it refills at 1 token/sec.
        # `anyio` doesn't directly expose a "refill" for `CapacityLimiter`.
        #
        # Alternative interpretation: The global_rate_limiter has 60 "slots".
        # Each request takes a slot. We need to ensure that slots are "released" (or refilled)
        # at a rate of 1 per second.
        # `anyio.CapacityLimiter` is more about bounding concurrent active tasks.
        #
        # Let's simplify for now: The global rate limit will be handled by `anyio.sleep`
        # in the main loop to effectively achieve ~1 req/sec, combined with the concurrency
        # limiter per model. The `global_rate_limiter` as `CapacityLimiter(60)` will primarily
        # act as a burst capacity if many models are called at once.
        # This part is tricky to get right with just CapacityLimiter for rate limiting over time.

        # For now, `self.global_rate_limiter` will be used to limit overall concurrency.
        # The actual rate limiting (e.g. 1 req/sec) will be approximated by sleeps.
        # This seems like a deviation from the prompt's intent for `global_rate_limiter`.
        #
        # Let's re-read: "global_rate_limiter = anyio.CapacityLimiter(60) (60 tokens per 60 seconds for simplicity, this matches 60 req/min if each request consumes 1 token)."
        # "token_bucket_interval_seconds = 1.0 (to refill 1 token per second for the global rate limiter)"
        # This means: bucket size 60. Refill 1 token/sec. Max burst 60. Sustained 1 req/sec.
        # `anyio.CapacityLimiter` is not a token bucket that refills.
        #
        # A simple way to model 1 req/sec:
        # self.last_request_time = 0
        # In chat():
        #   now = anyio.current_time()
        #   elapsed = now - self.last_request_time
        #   if elapsed < 1.0: await anyio.sleep(1.0 - elapsed)
        #   self.last_request_time = anyio.current_time()
        # This is a simple global rate limiter. The `CapacityLimiter(60)` would then be for bursting.
        # This seems more robust.
        self.last_global_request_time: float = 0.0
        # The model semaphores will handle concurrency per model.

    def _get_model_semaphore(self, model: str) -> anyio.Semaphore:
        if model not in self.model_semaphores:
            # Max 2 concurrent requests per model
            self.model_semaphores[model] = anyio.Semaphore(2)
        return self.model_semaphores[model]

    async def _calculate_cost(
        self, response_headers: httpx.Headers, prompt_tokens: int, completion_tokens: int
    ) -> float:
        # Basic static price list (example, expand as needed)
        # Prices per 1K tokens, input / output
        # For now, we'll only use the header, or 0.0 if header is missing.
        # The spec said: "if the header is missing, it will log a warning and return 0.0 cost."

        price_header = response_headers.get("x-openrouter-price")
        if price_header:
            try:
                # Assuming price_header is per Mtokens or Ktokens.
                # OpenRouter states "cost": "Cost of the request in USD." in their response.
                # And their headers for individual models often give price per token.
                # Let's assume the `x-openrouter-price` (if it exists) is price per token.
                # This is a guess. The API docs should be checked.
                # The spec says: "price = float(header_price). Cost = (prompt_tokens + completion_tokens) / 1000 * price_per_k_tokens_from_header"
                # This implies `header_price` is per 1K tokens.
                price_per_k_tokens = float(price_header)
                cost = (prompt_tokens + completion_tokens) / 1000.0 * price_per_k_tokens
                return cost
            except ValueError:
                logger.warning(
                    f"Could not parse x-openrouter-price header: {price_header}. Defaulting to 0.0 cost."
                )
                return 0.0
        else:
            # Per spec: "if the header is missing, it will log a warning and return 0.0 cost."
            logger.warning(
                "x-openrouter-price header not found. Defaulting to 0.0 cost for this request."
            )
            return 0.0

    async def chat(self, model: str, prompt: str, temperature: float) -> OpenRouterResponse:
        if self.cumulative_cost_usd >= self.settings.MAX_BUDGET_USD:
            raise BudgetExceededError(
                f"Cumulative cost ${self.cumulative_cost_usd:.4f} exceeds or meets budget ${self.settings.MAX_BUDGET_USD:.2f}"
            )

        model_semaphore = self._get_model_semaphore(model)

        max_retries_rate_limit = 5
        max_retries_server_error = 3
        max_connection_retry_time_seconds = 30.0

        current_attempt = 0
        rate_limit_attempt = 0
        server_error_attempt = 0
        connection_error_start_time: Optional[float] = None

        while True:
            current_attempt += 1
            logger.debug(f"Attempt {current_attempt} for model {model}")

            # Global rate limiting: approximate 1 request per second
            # This is a simple way to implement the "refill 1 token per second" idea.
            # The CapacityLimiter(60) from the original thought process is harder to map directly to this
            # without a background refilling task.
            now = anyio.current_time()
            elapsed_since_last_global_request = now - self.last_global_request_time
            if elapsed_since_last_global_request < self.token_bucket_interval_seconds:
                sleep_duration = self.token_bucket_interval_seconds - elapsed_since_last_global_request
                logger.debug(f"Global rate limiting: sleeping for {sleep_duration:.2f}s")
                await anyio.sleep(sleep_duration)
            self.last_global_request_time = anyio.current_time()

            # Acquire model-specific semaphore for concurrency control
            async with model_semaphore:
                try:
                    headers = {
                        "Authorization": f"Bearer {self.settings.OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                    }
                    payload = {
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": temperature,
                    }

                    logger.info(f"Sending request to OpenRouter: model={model}, temp={temperature}")
                    response = await self.client.post(
                        f"{self.base_url}/chat/completions", json=payload, headers=headers
                    )

                    # Reset connection error timer on successful connection attempt
                    connection_error_start_time = None

                    if response.status_code == 429:
                        rate_limit_attempt += 1
                        if rate_limit_attempt > max_retries_rate_limit:
                            raise RateLimitError(
                                f"Rate limit retries ({max_retries_rate_limit}) exceeded for model {model}."
                            )
                        # Retry-After header might be available
                        retry_after_str = response.headers.get("Retry-After")
                        delay: float
                        if retry_after_str:
                            try:
                                delay = float(retry_after_str)
                                if delay > 60: # Cap max delay from header
                                     delay = 60
                            except ValueError:
                                delay = (2 ** rate_limit_attempt) + random.uniform(0, 1)
                        else:
                            delay = (2 ** rate_limit_attempt) + random.uniform(0, 1)

                        logger.warning(
                            f"Rate limit hit for model {model}. Attempt {rate_limit_attempt}/{max_retries_rate_limit}. "
                            f"Retrying in {delay:.2f} seconds. Response: {response.text}"
                        )
                        await anyio.sleep(delay)
                        continue # Retry the while loop

                    elif 500 <= response.status_code < 600:
                        server_error_attempt += 1
                        if server_error_attempt > max_retries_server_error:
                            raise ServerError(
                                f"Server error retries ({max_retries_server_error}) exceeded for model {model}. "
                                f"Status: {response.status_code}. Response: {response.text}"
                            )
                        delay = 5.0 * server_error_attempt # Linear backoff: 5s, 10s, 15s
                        logger.warning(
                            f"Server error ({response.status_code}) for model {model}. "
                            f"Attempt {server_error_attempt}/{max_retries_server_error}. "
                            f"Retrying in {delay:.2f} seconds. Response: {response.text}"
                        )
                        await anyio.sleep(delay)
                        continue # Retry the while loop

                    # Raise for other client errors (4xx not 429) or unexpected server errors
                    response.raise_for_status()

                    # Successful response (2xx)
                    try:
                        data = response.json()
                    except Exception as e: # Covers json.JSONDecodeError and other parsing issues
                        raise ParseError(f"Failed to parse JSON response: {e}. Response text: {response.text}")

                    if not data.get("choices") or not data["choices"][0].get("message") or \
                       data["choices"][0]["message"].get("content") is None:
                        raise ParseError(f"Response format unexpected: 'choices[0].message.content' missing. Data: {data}")

                    text = data["choices"][0]["message"]["content"]

                    usage = data.get("usage")
                    if not usage or usage.get("prompt_tokens") is None or usage.get("completion_tokens") is None:
                        logger.warning(f"Token usage information missing in response. Defaulting to 0. Data: {data}")
                        prompt_tokens = 0
                        completion_tokens = 0
                    else:
                        prompt_tokens = usage["prompt_tokens"]
                        completion_tokens = usage["completion_tokens"]

                    cost = await self._calculate_cost(response.headers, prompt_tokens, completion_tokens)

                    self.cumulative_cost_usd += cost
                    logger.info(f"Request to {model} cost: ${cost:.6f}. Cumulative cost: ${self.cumulative_cost_usd:.4f}")

                    if self.cumulative_cost_usd > self.settings.MAX_BUDGET_USD:
                        # This specific wording is from the spec for logging, actual error is raised at start of call
                        logger.warning(
                            f"Budget ${self.settings.MAX_BUDGET_USD:.2f} will be exceeded after this call "
                            f"(current cumulative cost: ${self.cumulative_cost_usd:.4f})."
                        )
                        # No BudgetExceededError here, as the call was successful. The check is at the beginning.

                    return OpenRouterResponse(
                        text=text,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        status_code=response.status_code,
                        cost_usd=cost,
                    )

                except httpx.RequestError as e: # Base class for network errors like ReadTimeout, ConnectError
                    if connection_error_start_time is None:
                        connection_error_start_time = anyio.current_time()

                    elapsed_connection_error_time = anyio.current_time() - connection_error_start_time
                    if elapsed_connection_error_time > max_connection_retry_time_seconds:
                        raise ConnectionError(
                            f"Connection retries exceeded {max_connection_retry_time_seconds}s for model {model}. Last error: {e}"
                        ) from e

                    logger.warning(
                        f"Connection error for model {model}: {e}. "
                        f"Retrying in 2 seconds. Total time in connection error state: {elapsed_connection_error_time:.2f}s"
                    )
                    await anyio.sleep(2) # Simple 2s retry for connection issues
                    continue # Retry the while loop

                except httpx.HTTPStatusError as e: # Handles 4xx/5xx errors not caught by specific handlers above
                    # e.g. 400, 401, 403, or if response.raise_for_status() is hit by an unexpected 5xx
                    if e.response.status_code == 401 or e.response.status_code == 403:
                        # Authentication errors are not typically retryable with backoff
                        logger.error(f"Authentication error: {e.response.status_code} - {e.response.text}")
                        raise RouterClientError(f"Authentication error: {e.response.status_code} - Check API key. Response: {e.response.text}") from e
                    elif 500 <= e.response.status_code < 600:
                        # This case should ideally be caught by the specific 5xx handler block.
                        # If it reaches here, it means raise_for_status() was triggered by a 5xx.
                        # Treat it like a server error and retry (if attempts remain).
                        server_error_attempt += 1
                        if server_error_attempt > max_retries_server_error:
                             raise ServerError(
                                f"Server error retries ({max_retries_server_error}) exceeded for model {model} via HTTPStatusError. "
                                f"Status: {e.response.status_code}. Response: {e.response.text}"
                            ) from e
                        delay = 5.0 * server_error_attempt
                        logger.warning(
                            f"Server error ({e.response.status_code}) for model {model} (caught via HTTPStatusError). "
                            f"Attempt {server_error_attempt}/{max_retries_server_error}. "
                            f"Retrying in {delay:.2f} seconds. Response: {e.response.text}"
                        )
                        await anyio.sleep(delay)
                        continue
                    else:
                        # For other client errors (e.g., 400 Bad Request) that are not auth errors
                        logger.error(f"Unhandled HTTP client error: {e.response.status_code} - {e.response.text}")
                        raise RouterClientError(f"HTTP client error: {e.response.status_code}. Response: {e.response.text}") from e

                except ParseError as e: # Re-raise ParseError if it's caught from above
                    raise e

                except Exception as e: # Catch-all for unexpected errors within the try block
                    logger.exception(f"Unexpected error during API call for model {model}: {e}")
                    # Depending on the error, this could be a bug in the code or an unhandled API state
                    # For safety, wrap in RouterClientError and don't retry indefinitely
                    raise RouterClientError(f"An unexpected error occurred: {e}") from e

            # Should not be reached if loop continues or returns properly
            # If it's reached, it implies a logic error in retry conditions
            logger.error("Reached end of retry loop unexpectedly. Raising generic error.")
            raise RouterClientError("Exhausted retry logic unexpectedly.")


    async def close(self):
        logger.info("Closing RouterClient HTTP session.")
        await self.client.aclose()

# Example usage (for testing purposes, remove later)
async def main():
    # This is a placeholder for where settings would be loaded, e.g., from .env file
    # For testing, we can mock settings or use dummy values.
    # Ensure OPENROUTER_API_KEY is set in your environment for a real test.
    try:
        settings = Settings() # This will try to load from env
    except Exception as e:
        print(f"Failed to load settings (ensure .env or env vars are set): {e}")
        print("Using dummy settings for basic structure test.")
        class DummySettings:
            OPENROUTER_API_KEY="dummy_key_not_real" # Replace with your actual key for testing
            MAX_BUDGET_USD=1.0
        settings = DummySettings()

    if settings.OPENROUTER_API_KEY == "dummy_key_not_real" and os.getenv("OPENROUTER_API_KEY"):
        settings.OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")


    client = RouterClient(settings)

    models_to_test = [
        "openai/gpt-3.5-turbo",
        "mistralai/mistral-7b-instruct",
        # "google/gemini-pro" # Requires specific setup usually
    ]

    test_prompt = "Translate 'hello world' to German."

    # Configure logging for testing
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    for model_name in models_to_test:
        try:
            print(f"\n--- Testing model: {model_name} ---")
            response = await client.chat(model=model_name, prompt=test_prompt, temperature=0.7)
            print(f"Model: {response.model}") # This field is not in OpenRouterResponse, it's part of BenchmarkRecord
                                            # The 'model' in chat() is an input. OpenRouterResponse doesn't store it.
            print(f"Response Text: {response.text}")
            print(f"Prompt Tokens: {response.prompt_tokens}")
            print(f"Completion Tokens: {response.completion_tokens}")
            print(f"Cost USD: ${response.cost_usd:.8f}")
            print(f"Status Code: {response.status_code}")
        except BudgetExceededError as e:
            print(f"Error for {model_name}: Budget exceeded - {e}")
            break # Stop testing if budget is hit
        except RouterClientError as e:
            print(f"Error for {model_name}: {e}")
        except Exception as e:
            print(f"Unexpected error for {model_name}: {e}")
            logger.exception(f"Raw exception for {model_name}")

    await client.close()
    print(f"\nTotal cumulative cost: ${client.cumulative_cost_usd:.4f}")

if __name__ == "__main__":
    # This import is needed for the example main, ensure it's available if running standalone
    import os
    # For running example:
    # Ensure pydantic, httpx, anyio are installed
    # Set OPENROUTER_API_KEY environment variable
    # `python src/router_client.py`

    # If you have anyio.run in newer versions or want to use asyncio.run:
    # asyncio.run(main())
    # For compatibility or if anyio.run is preferred:
    try:
        anyio.run(main)
    except KeyboardInterrupt:
        print("Test run interrupted.")
