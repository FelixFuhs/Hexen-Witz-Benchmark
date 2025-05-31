import asyncio
import logging
import json # For loading raw generation results
from pathlib import Path
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from pydantic import ValidationError # For handling GenerationResult parsing errors

from src.config import Settings
from src.router_client import RouterClient, BudgetExceededError
from src.generator import run_generations_for_model # Renamed from run_generations_for_model
from src.judge import judge_response, load_judge_prompt_template
from src.models import GenerationResult, BenchmarkRecord # Summary not directly used here but is part of models
from src.storage.files import save_benchmark_record, write_meta_json
from src.storage.database import create_connection, execute_ddl, insert_benchmark_record

# Basic logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()] # Ensure logs go to console
)
logger = logging.getLogger(__name__)


async def run_benchmark(
    run_id: Optional[str] = None,
    models_to_run: Optional[List[str]] = None,
    num_runs_per_model: int = 1,
    config_file: Optional[str] = None, # Changed from config_path to align with Pydantic settings
    base_output_dir_str: str = "benchmarks_output"
) -> None:
    """
    Main orchestration function for running the benchmark.
    Generates responses, judges them, and stores results in files and SQLite DB.
    """
    current_run_id = run_id if run_id else f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    base_output_path = Path(base_output_dir_str)
    run_output_path = base_output_path / current_run_id

    # Ensure base run directory exists (storage.files.ensure_dir_structure will also do this, but good to have early)
    try:
        run_output_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Output directory for run {current_run_id}: {run_output_path}")
    except OSError as e:
        logger.error(f"Failed to create base output directory {run_output_path}: {e}. Aborting.")
        return

    logger.info(f"Starting benchmark run: {current_run_id}")

    # Load settings
    try:
        # Pydantic's BaseSettings will automatically look for a .env file if _env_file is not specified or is None.
        # If config_file is provided, it's passed as the _env_file argument.
        settings = Settings(_env_file=config_file) if config_file else Settings()
        logger.info(f"Settings loaded. Judge model: {settings.JUDGE_MODEL_NAME}, Max budget: ${settings.MAX_BUDGET_USD}")
    except Exception as e: # Catch errors during settings loading (e.g., if .env file has issues or required vars missing)
        logger.error(f"Error loading settings: {e}. Aborting run.", exc_info=True)
        return

    # Write metadata (excluding sensitive fields)
    # Use model_dump(exclude=...) for Pydantic v2
    serializable_settings = settings.model_dump(exclude={'OPENROUTER_API_KEY'})
    write_meta_json(
        run_id=current_run_id,
        config_settings=serializable_settings,
        base_path_str=base_output_dir_str
    )

    router_client: Optional[RouterClient] = None
    db_conn: Optional[sqlite3.Connection] = None # type: ignore # sqlite3 not imported here directly for brevity

    try:
        router_client = RouterClient(settings)

        # Database Setup
        db_file = str(run_output_path / f"{current_run_id}_benchmark_data.sqlite")
        # Use the database module's create_connection
        db_conn = create_connection(db_file) # from src.storage.database
        if not db_conn or not execute_ddl(db_conn): # from src.storage.database
            logger.error("Failed to initialize SQLite database. Aborting run.")
            # No need to close router_client or db_conn here, finally block will handle
            return # Exit if DB setup fails

        # Model selection
        if not models_to_run:
            models_to_run = ["mistralai/mistral-7b-instruct"] # Default test model
            logger.info(f"No models specified, using default: {models_to_run}")

        judge_prompt_template_content = load_judge_prompt_template() # from src.judge
        judge_llm_name = settings.JUDGE_MODEL_NAME

        # --- Generation Phase ---
        logger.info(f"--- Starting Generation Phase for run {current_run_id} ---")
        for model_name in models_to_run:
            logger.info(f"Running generations for model: {model_name} ({num_runs_per_model} runs)")
            try:
                await run_generations_for_model( # from src.generator
                    router_client=router_client,
                    model=model_name,
                    num_runs=num_runs_per_model,
                    current_run_id=current_run_id,
                    base_output_dir=base_output_dir_str # Corrected param name
                )
            except BudgetExceededError as be:
                logger.error(f"Budget exceeded during generation for model {model_name}: {be}. Stopping further generations.")
                break # Stop generating more models if budget is hit
            except Exception as e:
                logger.error(f"Error during generation for model {model_name}: {e}", exc_info=True)
                # Decide if we should continue with other models or stop
                # For now, continue with other models if one fails.
        logger.info(f"--- Generation Phase Complete for run {current_run_id} ---")

        # --- Judging Phase ---
        logger.info(f"--- Starting Judging Phase for run {current_run_id} ---")
        raw_results_path = run_output_path / "raw"
        processed_files_count = 0
        judged_records_count = 0

        if not raw_results_path.exists() or not any(raw_results_path.iterdir()):
            logger.warning(f"No raw generation files found in {raw_results_path}. Skipping judging phase.")
        else:
            for gen_file_path in raw_results_path.glob("*.json"):
                try:
                    logger.debug(f"Processing raw result file: {gen_file_path.name}")
                    with gen_file_path.open("r", encoding="utf-8") as f:
                        gen_data_dict = json.load(f)

                    # Validate data with Pydantic model
                    generation_result_obj = GenerationResult(**gen_data_dict)
                    processed_files_count += 1

                    logger.info(f"Judging result for {generation_result_obj.model} run {generation_result_obj.run}")
                    judge_score_obj = await judge_response( # from src.judge
                        router_client=router_client,
                        generation_result=generation_result_obj,
                        judge_model_name=judge_llm_name,
                        judge_prompt_template=judge_prompt_template_content
                    )

                    if judge_score_obj:
                        benchmark_record_obj = BenchmarkRecord(
                            generation=generation_result_obj, judge=judge_score_obj
                        )
                        save_benchmark_record( # from src.storage.files
                            record=benchmark_record_obj,
                            run_id=current_run_id,
                            base_path_str=base_output_dir_str
                        )
                        if db_conn: # Should be true if we reached here
                            insert_benchmark_record(db_conn, benchmark_record_obj, current_run_id) # from src.storage.database
                        logger.info(f"Saved and stored judged record for {generation_result_obj.model} run {generation_result_obj.run}")
                        judged_records_count += 1
                    else:
                        logger.warning(
                            f"Judging skipped or failed for {generation_result_obj.model} "
                            f"run {generation_result_obj.run}. Raw file: {gen_file_path.name}"
                        )
                except json.JSONDecodeError as e:
                    logger.error(f"Error decoding JSON from {gen_file_path.name}: {e}")
                except ValidationError as e: # Pydantic validation error for GenerationResult
                    logger.error(f"Data validation error for {gen_file_path.name}: {e}")
                except BudgetExceededError as be: # Catch budget error during judging
                    logger.error(f"Budget exceeded during judging of file {gen_file_path.name}: {be}. Stopping further judging.")
                    break # Stop judging if budget is hit
                except Exception as e:
                    logger.error(f"Error processing file {gen_file_path.name} for judging: {e}", exc_info=True)

            logger.info(f"Judging phase complete. Processed {processed_files_count} generated files. Created {judged_records_count} judged records.")

    except BudgetExceededError as be: # Catch budget error from initial client setup or if it propagates
        logger.critical(f"Budget exceeded for run {current_run_id}: {be}. Run halted.", exc_info=True)
    except Exception as e:
        logger.critical(f"Critical error during benchmark run {current_run_id}: {e}", exc_info=True)
    finally:
        logger.info(f"Closing resources for run {current_run_id}...")
        if db_conn:
            try:
                db_conn.close()
                logger.info("SQLite connection closed.")
            except Exception as e:
                logger.error(f"Error closing SQLite connection: {e}", exc_info=True)
        if router_client:
            try:
                await router_client.close()
                logger.info("RouterClient connection closed.")
            except Exception as e:
                logger.error(f"Error closing RouterClient: {e}", exc_info=True)
        logger.info(f"Benchmark run {current_run_id} finished.")


if __name__ == "__main__":
    # Example of how to run:
    # Ensure OPENROUTER_API_KEY is set in your environment or a .env file.
    # You can create a .env file with:
    # OPENROUTER_API_KEY="your_actual_api_key_here"
    # MAX_BUDGET_USD=5.0
    # JUDGE_MODEL_NAME="mistralai/mistral-small-latest" # Cheaper judge for testing

    logger.info("Starting main.py test run using __main__ block.")

    # Create dummy prompt files if they don't exist, for the main test to run smoothly
    Path("src/prompts").mkdir(parents=True, exist_ok=True)
    benchmark_prompt_path = Path("src/prompts/benchmark_prompt.md")
    judge_prompt_path = Path("src/prompts/judge_checklist.md")

    if not benchmark_prompt_path.exists() or benchmark_prompt_path.read_text().strip() == "":
        benchmark_prompt_path.write_text(
            "Erzähl einen Witz über einen Informatiker und einen Physiker.\n"
            "Antworte im Stil eines Comedians und gib eine Zusammenfassung deiner Antwort in EXAKT diesem Format:\n"
            "### ZUSAMMENFASSUNG\n- Gewünscht: <Zusammenfassung Wunsch>\n- Bekommen: <Zusammenfassung Antwort>",
            encoding="utf-8"
        )
        logger.info(f"Created dummy benchmark prompt at {benchmark_prompt_path}")

    if not judge_prompt_path.exists() or judge_prompt_path.read_text().strip() == "":
        judge_prompt_path.write_text(
            """Bewerte die phonetische Ähnlichkeit und den Witz der folgenden Antwort.
WUNSCH: [aus der Antwort extrahiert]
ERGEBNIS: [aus der Antwort extrahiert]
VOLLSTAENDIGE ANTWORT DES GETESTETEN MODELLS: [hier die komplette Antwort des LLMs einfügen]
Gib deine Bewertung als JSON-Objekt zurück. Beispiel:
```json
{
  "phonetische_aehnlichkeit": 30, "anzueglichkeit": 5, "logik": 15, "kreativitaet": 18, "gesamt": 68,
  "begruendung": { "phonetische_aehnlichkeit": "Sehr gut.", "gesamt": "Solide."}
}
```""",
            encoding="utf-8"
        )
        logger.info(f"Created dummy judge prompt at {judge_prompt_path}")

    # Define test parameters
    test_run_id_main = f"main_test_run_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    # Using a very cheap or free model for testing the pipeline
    # test_models = ["mistralai/mistral-tiny", "nousresearch/nous-capybara-7b"]
    test_models = ["mistralai/mistral-7b-instruct"] # Often available and performs okay for structure tests
    # test_models = ["openai/gpt-3.5-turbo"] # If you have OpenAI credits

    try:
        asyncio.run(run_benchmark(
            run_id=test_run_id_main,
            models_to_run=test_models,
            num_runs_per_model=2, # Generate 2 jokes per model
            base_output_dir_str="benchmarks_main_output" # Separate output for these tests
        ))
    except Exception as e:
        logger.critical(f"Error running benchmark from __main__: {e}", exc_info=True)
    finally:
        logger.info("Finished main.py test run from __main__ block.")

```
Key changes in this implementation:
- **Imports**: Added `json` for loading raw results, `ValidationError` from Pydantic.
- **Logging**: Basic logging config added at the top of `main.py`.
- **Settings Loading**: Uses `Settings(_env_file=config_file if config_file else None)` which correctly leverages Pydantic's `.env` file handling. If `config_file` is `None`, Pydantic looks for a default `.env`.
- **Parameter Name**: Changed `config_path` to `config_file` in `run_benchmark` to match Pydantic's `_env_file` parameter name for clarity.
- **Error Handling**: Added `try-except` blocks for settings loading and initial directory creation. Added `BudgetExceededError` handling in generation and judging loops.
- **Resource Management**: Ensured `RouterClient` and `db_conn` are closed in the `finally` block.
- **Clarity**: Renamed `base_output_dir` in `run_generations_for_model` call to match its definition in `generator.py`.
- **Raw Results Processing**: Added a check to see if `raw_results_path` exists and has files before attempting to glob.
- **Pydantic Validation**: Added `GenerationResult(**gen_data_dict)` to validate the loaded JSON data against the Pydantic model.
- **`__main__` Block**:
    - Creates dummy prompt files if they are missing or empty.
    - Sets a specific output directory for tests run from `main.py`.
    - Runs with `mistralai/mistral-7b-instruct` (a generally available model) and `num_runs_per_model=2`.

This structure seems robust for the main benchmark execution. I'll submit the report.
