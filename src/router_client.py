import httpx
import anyio
import asyncio # For asyncio.sleep, though anyio.sleep is preferred
import random
from typing import Dict, Any, Optional
from datetime import datetime # Potentially for time-based calculations
import logging
import os # For the example main function

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
        # Global rate limiter related attributes (from your original file)
        self.global_rate_limiter = anyio.CapacityLimiter(60) 
        self.token_bucket_interval_seconds = 1.0 
        self.last_global_request_time: float = 0.0

    def _get_model_semaphore(self, model: str) -> anyio.Semaphore:
        if model not in self.model_semaphores:
            # Max 2 concurrent requests per model (from your original file)
            self.model_semaphores[model] = anyio.Semaphore(2)
        return self.model_semaphores[model]

    async def _calculate_cost(
        self, response_headers: httpx.Headers, prompt_tokens: int, completion_tokens: int
    ) -> float:
        price_header = response_headers.get("x-openrouter-price")
        if price_header:
            try:
                # Assuming price_header is per K tokens (from your original file logic)
                price_per_k_tokens = float(price_header)
                cost = (prompt_tokens + completion_tokens) / 1000.0 * price_per_k_tokens
                return cost
            except ValueError:
                logger.warning(
                    f"Could not parse x-openrouter-price header: {price_header}. Defaulting to 0.0 cost."
                )
                return 0.0
        else:
            # Per spec: "if the header is missing, it will log a warning and return 0.0 cost." (from your original file)
            logger.warning(
                "x-openrouter-price header not found. Defaulting to 0.0 cost for this request."
            )
            return 0.0

    async def chat(self, model: str, prompt: str, temperature: float, **kwargs: Any) -> OpenRouterResponse:
        if self.cumulative_cost_usd >= self.settings.MAX_BUDGET_USD:
            raise BudgetExceededError(
                f"Cumulative cost ${self.cumulative_cost_usd:.4f} exceeds or meets budget ${self.settings.MAX_BUDGET_USD:.2f}"
            )

        model_semaphore = self._get_model_semaphore(model)

        # Retry parameters (from your original file)
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

            # Global rate limiting (from your original file)
            now = anyio.current_time()
            elapsed_since_last_global_request = now - self.last_global_request_time
            if elapsed_since_last_global_request < self.token_bucket_interval_seconds:
                sleep_duration = self.token_bucket_interval_seconds - elapsed_since_last_global_request
                logger.debug(f"Global rate limiting: sleeping for {sleep_duration:.2f}s")
                await anyio.sleep(sleep_duration)
            self.last_global_request_time = anyio.current_time()

            # Acquire model-specific semaphore (from your original file)
            async with model_semaphore:
                try:
                    headers = {
                        "Authorization": f"Bearer {self.settings.OPENROUTER_API_KEY}",
                        "Content-Type": "application/json",
                    }
                    
                    # Base payload construction (from your original file, adding **kwargs)
                    payload: Dict[str, Any] = {
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "temperature": temperature,
                        **kwargs, # Apply any extra parameters passed by the caller
                    }

                    # ------------------------------------------------------------------
                    # 🛠 Work-around: disable reasoning-summary for OpenAI o-series
                    #    (Based on your research and proposed patch)
                    # ------------------------------------------------------------------
                    # Check if the model is an OpenAI o-series model and if reasoning parameters
                    # haven't already been set by the caller via **kwargs.
                    if model.lower().startswith("openai/o") and \
                       "include_reasoning" not in payload and \
                       "reasoning" not in payload: # Simplified check: if caller sets 'reasoning', they control it.
                        
                        # Tell OpenRouter NOT to add reasoning.summary=auto (or similar)
                        payload["include_reasoning"] = False
                        logger.info(f"Applied 'include_reasoning': False for OpenAI o-series model {model}")
                        
                        # Optionally constrain effort.
                        # Using setdefault on the payload itself for the 'reasoning' key.
                        # This will add {'effort': 'low'} only if 'reasoning' is not already a key.
                        # If 'include_reasoning: false' makes OpenRouter ignore any 'reasoning' block,
                        # this might be moot, but it aligns with the desire to specify low effort if possible.
                        current_reasoning_config = payload.setdefault("reasoning", {})
                        if isinstance(current_reasoning_config, dict): # Ensure it's a dict
                           current_reasoning_config.setdefault("effort", "low") # Add 'effort' if not present
                           logger.info(f"Ensured 'reasoning.effort': 'low' for model {model} if reasoning block present/added.")
                        else:
                            # This case should ideally not happen if 'reasoning' wasn't in payload initially
                            logger.warning(f"Cannot set 'reasoning.effort' for model {model} as payload['reasoning'] is not a dict.")
                    # ------------------------------------------------------------------

                    logger.info(f"Sending request to OpenRouter: model={model}, temp={temperature}, payload keys: {list(payload.keys())}")
                    response = await self.client.post(
                        f"{self.base_url}/chat/completions", json=payload, headers=headers
                    )

                    # Reset connection error timer on successful connection attempt (from your original file)
                    connection_error_start_time = None

                    # Specific HTTP status code handling (from your original file)
                    if response.status_code == 429: # Rate limit
                        rate_limit_attempt += 1
                        if rate_limit_attempt > max_retries_rate_limit:
                            raise RateLimitError(
                                f"Rate limit retries ({max_retries_rate_limit}) exceeded for model {model}."
                            )
                        retry_after_str = response.headers.get("Retry-After")
                        delay: float
                        if retry_after_str:
                            try:
                                delay = float(retry_after_str)
                                if delay > 60: # Cap max delay
                                     delay = 60
                            except ValueError: # Fallback if Retry-After is not a number
                                delay = (2 ** rate_limit_attempt) + random.uniform(0, 1) # Exponential backoff
                        else:
                            delay = (2 ** rate_limit_attempt) + random.uniform(0, 1) # Exponential backoff

                        logger.warning(
                            f"Rate limit hit for model {model}. Attempt {rate_limit_attempt}/{max_retries_rate_limit}. "
                            f"Retrying in {delay:.2f} seconds. Response: {response.text}"
                        )
                        await anyio.sleep(delay)
                        continue # Retry the while loop

                    elif 500 <= response.status_code < 600: # Server error
                        server_error_attempt += 1
                        if server_error_attempt > max_retries_server_error:
                            raise ServerError(
                                f"Server error retries ({max_retries_server_error}) exceeded for model {model}. "
                                f"Status: {response.status_code}. Response: {response.text}"
                            )
                        delay = 5.0 * server_error_attempt # Linear backoff (e.g., 5s, 10s, 15s)
                        logger.warning(
                            f"Server error ({response.status_code}) for model {model}. "
                            f"Attempt {server_error_attempt}/{max_retries_server_error}. "
                            f"Retrying in {delay:.2f} seconds. Response: {response.text}"
                        )
                        await anyio.sleep(delay)
                        continue # Retry the while loop

                    # Raise for other client errors (4xx not 429) or unexpected server errors
                    # This is where the 400 error for "reasoning summaries" would be caught if the patch doesn't work
                    response.raise_for_status()

                    # Successful response (2xx) processing (from your original file)
                    try:
                        data = response.json()
                    except Exception as e: # Covers json.JSONDecodeError and other parsing issues
                        raise ParseError(f"Failed to parse JSON response: {e}. Response text: {response.text}")

                    # Validate response structure (from your original file)
                    if not data.get("choices") or not data["choices"][0].get("message") or \
                       data["choices"][0]["message"].get("content") is None:
                        raise ParseError(f"Response format unexpected: 'choices[0].message.content' missing. Data: {data}")

                    text = data["choices"][0]["message"]["content"]

                    # Token usage and cost calculation (from your original file)
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

                    # Budget check after successful call (logging only, main check is at start) (from your original file)
                    if self.cumulative_cost_usd > self.settings.MAX_BUDGET_USD:
                        logger.warning(
                            f"Budget ${self.settings.MAX_BUDGET_USD:.2f} will be exceeded after this call "
                            f"(current cumulative cost: ${self.cumulative_cost_usd:.4f})."
                        )
                    
                    return OpenRouterResponse(
                        text=text,
                        prompt_tokens=prompt_tokens,
                        completion_tokens=completion_tokens,
                        status_code=response.status_code,
                        cost_usd=cost,
                    )

                # Exception handling (from your original file structure)
                except httpx.RequestError as e: # Base class for network errors
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
                    await anyio.sleep(2) # Simple retry for connection issues
                    continue # Retry the while loop

                except httpx.HTTPStatusError as e: # Handles 4xx/5xx from raise_for_status()
                    if e.response.status_code == 401 or e.response.status_code == 403: # Auth errors
                        logger.error(f"Authentication error: {e.response.status_code} - {e.response.text}")
                        raise RouterClientError(f"Authentication error: {e.response.status_code} - Check API key. Response: {e.response.text}") from e
                    elif 500 <= e.response.status_code < 600: # Should be caught by earlier 5xx block, but as fallback
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
                    else: # Other client errors (e.g., 400 Bad Request)
                        logger.error(f"HTTP client error: {e.response.status_code} - {e.response.text} for model {model}")
                        if "reasoning summaries" in e.response.text and "organization must be verified" in e.response.text:
                             logger.error(
                                f"OpenAI organization verification required for 'reasoning summaries' with model {model}. "
                                "This specific 400 error might not be retryable without addressing the verification or API parameters. "
                                "Ensure `include_reasoning: false` (or similar fix) is correctly sent and respected for o-series models."
                            )
                        raise RouterClientError(f"HTTP client error: {e.response.status_code}. Response: {e.response.text}") from e
                
                except ParseError as e: # Re-raise specific ParseError
                    raise e

                except Exception as e: # Catch-all for unexpected errors within the try-except block
                    logger.exception(f"Unexpected error during API call for model {model}: {e}")
                    raise RouterClientError(f"An unexpected error occurred: {e}") from e

            # This part of the loop should ideally not be reached if logic is correct
            logger.error(f"Reached end of retry loop unexpectedly for model {model}. Raising generic error.")
            raise RouterClientError(f"Exhausted retry logic unexpectedly for model {model}.")


    async def close(self):
        logger.info("Closing RouterClient HTTP session.")
        await self.client.aclose()

# Example usage (from your original file, with minor adjustments for clarity)
async def main():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    try:
        # Attempt to load settings, ensuring OPENROUTER_API_KEY is present for actual test calls
        api_key_from_env = os.getenv("OPENROUTER_API_KEY")
        if not api_key_from_env: # Handles if key is missing or empty string
            logger.error("OPENROUTER_API_KEY environment variable not found or empty. Real API calls in test main will fail.")
            # For local testing without an API key, you might want to raise an error or use a mock
            # For this example, we'll proceed with a dummy key for structural testing if no key is found.
            settings = Settings(OPENROUTER_API_KEY="YOUR_OPENROUTER_API_KEY_OR_DUMMY", MAX_BUDGET_USD=1.0)
            if settings.OPENROUTER_API_KEY == "YOUR_OPENROUTER_API_KEY_OR_DUMMY":
                 logger.warning("Using a placeholder API key for settings in test main.")
        else:
            settings = Settings(OPENROUTER_API_KEY=api_key_from_env) # MAX_BUDGET_USD will use default from Settings
            logger.info(f"Settings loaded for test main. Max budget: ${settings.MAX_BUDGET_USD}")

    except Exception as e: # Catches Pydantic's ValidationError if OPENROUTER_API_KEY is missing and no default
        logger.error(f"Failed to initialize Settings for test main (OPENROUTER_API_KEY issue?): {e}", exc_info=True)
        # Fallback for structural execution of the test, API calls would fail if key is truly dummy/missing
        settings = Settings(OPENROUTER_API_KEY="dummy_key_for_structural_test", MAX_BUDGET_USD=1.0)


    client = RouterClient(settings)

    models_to_test = [
        "openai/o4-mini",
        # "mistralai/mistral-7b-instruct", # Example of a non-o-series model
    ]
    test_prompt = "What is the capital of Germany and what is its significance?"

    for model_name in models_to_test:
        try:
            print(f"\n--- Testing model: {model_name} ---")
            # Example: pass an extra, normally unused kwarg to demonstrate **kwargs
            # For o4-mini, the 'reasoning' or 'include_reasoning' will be handled internally by the patch
            response = await client.chat(model=model_name, prompt=test_prompt, temperature=0.7, top_p=0.9) 
            print(f"Response Text: {response.text}")
            print(f"Prompt Tokens: {response.prompt_tokens}")
            print(f"Completion Tokens: {response.completion_tokens}")
            print(f"Cost USD: ${response.cost_usd:.8f}")
            print(f"Status Code: {response.status_code}")
        except BudgetExceededError as e:
            print(f"Error for {model_name}: Budget exceeded - {e}")
            break 
        except RouterClientError as e:
            print(f"RouterClientError for {model_name}: {e}")
        except Exception as e:
            print(f"Generic Exception for {model_name}: {e}")
            logger.exception(f"Unhandled exception in test main loop for {model_name}")

    await client.close()
    print(f"\nTotal cumulative cost during test: ${client.cumulative_cost_usd:.4f}")

if __name__ == "__main__":
    # This ensures the anyio event loop runs the async main function
    try:
        anyio.run(main)
    except KeyboardInterrupt:
        print("Test run interrupted by user.")
    except Exception as e:
        logger.critical(f"Critical error in __main__ execution: {e}", exc_info=True)