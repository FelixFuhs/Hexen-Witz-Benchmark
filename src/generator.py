import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List

from src.router_client import RouterClient # Assuming OpenRouterResponse is implicitly handled if not directly imported
from src.storage.files import save_generation_result
from src.models import GenerationResult, Summary # OpenRouterResponse is defined in models.py
from src.extractor import extract_summary, SummaryParseError
from src.config import Settings

logger = logging.getLogger(__name__)

def load_benchmark_prompt(file_path: str = "src/prompts/benchmark_prompt.md") -> str:
    """
    Loads the content of the benchmark prompt file.
    """
    try:
        prompt_path = Path(file_path)
        content = prompt_path.read_text(encoding="utf-8")
        logger.info(f"Successfully loaded benchmark prompt from {file_path}")
        return content
    except FileNotFoundError:
        logger.error(f"Benchmark prompt file not found at {file_path}")
        raise
    except Exception as e:
        logger.error(f"Error loading benchmark prompt from {file_path}: {e}")
        raise


async def generate_joke(
    router_client: RouterClient,
    model: str,
    prompt: str,
    run_number: int,
    temperature: float = 0.7,
) -> GenerationResult:
    """
    Generates a joke using the specified model and prompt, then attempts to extract a summary.
    """
    logger.info(f"Generating joke for model {model}, run {run_number}, temperature {temperature}.")

    # response_data will be an OpenRouterResponse TypedDict
    response_data = await router_client.chat(
        model=model, prompt=prompt, temperature=temperature
    )

    extracted_summary: Optional[Summary] = None
    try:
        # Use dictionary key access for TypedDict
        if response_data['text']:
            extracted_summary = extract_summary(response_data['text'])
            logger.info(f"Successfully extracted summary for model {model}, run {run_number}.")
        else:
            logger.warning(f"Response text is empty for model {model}, run {run_number}. Skipping summary extraction.")
    except SummaryParseError as e:
        logger.warning(
            f"Could not parse summary for model {model}, run {run_number}: {e}. "
            f"Full response will be saved without summary. Response text length: {len(response_data['text'])}."
        )
    except Exception as e:
        logger.error(
            f"Unexpected error during summary extraction for model {model}, run {run_number}: {e}",
            exc_info=True
        )

    timestamp = datetime.now(timezone.utc)

    return GenerationResult(
        model=model,
        run=run_number,
        summary=extracted_summary,
        # Use dictionary key access here as well
        full_response=response_data['text'],
        prompt_tokens=response_data['prompt_tokens'],
        completion_tokens=response_data['completion_tokens'],
        cost_usd=response_data['cost_usd'],
        timestamp=timestamp,
    )


async def run_generations_for_model(
    router_client: RouterClient,
    model: str,
    num_runs: int,
    current_run_id: str,
    benchmark_prompt_file: str = "src/prompts/benchmark_prompt.md",
    base_output_dir: str = "benchmarks_output",
) -> List[GenerationResult]:
    """
    Orchestrates the generation of multiple joke attempts for a single model.
    Saves each result using storage.files.save_generation_result.
    """
    try:
        benchmark_prompt_content = load_benchmark_prompt(benchmark_prompt_file)
    except Exception:
        logger.error(
            f"Cannot proceed with generations for model {model} in run {current_run_id} "
            "due to prompt loading failure."
        )
        return []

    results: List[GenerationResult] = []

    logger.info(
        f"Starting generations for model {model}, run_id {current_run_id}. "
        f"Output directory: {Path(base_output_dir) / current_run_id}"
    )

    for i in range(num_runs):
        run_num = i + 1
        logger.info(f"Starting generation attempt {run_num}/{num_runs} for model {model} in run {current_run_id}.")
        try:
            result = await generate_joke(
                router_client, model, benchmark_prompt_content, run_num
            )
            results.append(result)

            save_generation_result(
                result=result,
                run_id=current_run_id,
                base_path_str=base_output_dir
            )
            logger.info(
                f"Saved result and cost for model {model}, attempt {result.run} "
                f"in run_id {current_run_id} via storage.files."
            )

        except Exception as e:
            logger.error(
                f"Failed to generate joke for model {model}, run {run_num}: {e}",
                exc_info=True
            )

    logger.info(f"Completed {len(results)} generation runs for model {model}.")
    return results


async def main_test():
    """
    Example function to test generator functionality.
    Requires OPENROUTER_API_KEY environment variable.
    """
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    logger.info("Starting generator test run...")

    dummy_prompt_file = Path("src/prompts/benchmark_prompt.md")
    dummy_prompt_file.parent.mkdir(parents=True, exist_ok=True)
    if not dummy_prompt_file.exists() or dummy_prompt_file.read_text(encoding="utf-8").strip() == "":
        dummy_prompt_file.write_text(
            "Was ist der Unterschied zwischen einem Informatiker und einem Physiker?\n\n"
            "Antworte im Stil eines sehr schlechten Comedians und gib eine Zusammenfassung deiner Antwort in EXAKT diesem Format:\n"
            "### ZUSAMMENFASSUNG\n"
            "- Gewünscht: <kurze Zusammenfassung der gewünschten Antwort>\n"
            "- Bekommen: <kurze Zusammenfassung der erhaltenen Antwort>",
            encoding="utf-8"
        )
        logger.info(f"Created/updated dummy prompt file at {dummy_prompt_file}")

    try:
        settings = Settings()
        if not settings.OPENROUTER_API_KEY or settings.OPENROUTER_API_KEY == "dummy_key_not_real":
            logger.warning("OPENROUTER_API_KEY not found or is a dummy value. Real API calls will fail.")
            import os
            env_api_key = os.getenv("OPENROUTER_API_KEY")
            if env_api_key:
                settings.OPENROUTER_API_KEY = env_api_key
                logger.info("Loaded OPENROUTER_API_KEY from environment variable.")
            else:
                logger.error("OPENROUTER_API_KEY is not set. Cannot run main_test with API calls.")
                return
    except Exception as e:
        logger.error(f"Failed to initialize Settings (OPENROUTER_API_KEY missing?): {e}")
        return

    client = RouterClient(settings)
    try:
        test_model = "mistralai/mistral-7b-instruct"
        test_run_id = f"generator_main_test_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        output_dir = "benchmarks_output_generator_test"

        logger.info(f"Running generations for model: {test_model}, run_id: {test_run_id}")
        results = await run_generations_for_model(
            router_client=client,
            model=test_model,
            num_runs=2,
            current_run_id=test_run_id,
            benchmark_prompt_file=str(dummy_prompt_file),
            base_output_dir=output_dir
        )

        if results:
            logger.info(f"Successfully generated {len(results)} results for run_id {test_run_id}.")
            logger.info(f"Test results saved in {Path(output_dir) / test_run_id}")
            for res_idx, res in enumerate(results):
                print(f"  Result {res_idx + 1}: Model={res.model}, Run={res.run}, Summary={res.summary is not None}, Cost=${res.cost_usd:.6f}")
        else:
            logger.warning(f"No results were generated for run_id {test_run_id}.")

    except Exception as e:
        logger.error(f"An error occurred during the main_test: {e}", exc_info=True)
    finally:
        logger.info("Closing router client...")
        await client.close()
        logger.info("Router client closed.")

if __name__ == "__main__":
    asyncio.run(main_test())