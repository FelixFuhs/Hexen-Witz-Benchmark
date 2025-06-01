import asyncio
import logging
import json # For loading raw generation results
from pathlib import Path # Ensure Path is imported
from datetime import datetime, timezone
from typing import List, Optional, Dict, Any

from pydantic import ValidationError # For handling GenerationResult parsing errors

from src.config import Settings
from src.router_client import RouterClient, BudgetExceededError
from src.generator import run_generations_for_model
from src.judge import judge_response, load_judge_prompt_template
from src.models import GenerationResult, BenchmarkRecord
from src.storage.files import save_benchmark_record, write_meta_json
from src.storage.database import create_connection, execute_ddl, insert_benchmark_record
import sqlite3

# Basic logging configuration
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)


async def run_benchmark(
    run_id: Optional[str] = None,
    models_to_run: Optional[List[str]] = None,
    num_runs_per_model: int = 1,
    config_file: Optional[str] = None,
    base_output_dir_str: str = "benchmarks_output"
) -> None:
    """
    Main orchestration function for running the benchmark.
    Generates responses, judges them, and stores results in files and SQLite DB.
    """
    current_run_id = run_id if run_id else f"run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
    base_output_path = Path(base_output_dir_str)
    run_output_path = base_output_path / current_run_id

    try:
        run_output_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Output directory for run {current_run_id}: {run_output_path}")
    except OSError as e:
        logger.error(f"Failed to create base output directory {run_output_path}: {e}. Aborting.")
        return

    logger.info(f"Starting benchmark run: {current_run_id}")

    # Load settings
    try:
        if config_file:
            logger.info(f"Attempting to load settings from specified config file: {config_file}")
            settings = Settings(_env_file=config_file)
        else:
            env_path = Path.cwd() / ".env"
            if env_path.exists() and env_path.is_file():
                logger.info(f"Attempting to load settings from default .env file: {env_path}")
                settings = Settings(_env_file=env_path)
            else:
                logger.warning(f"Default .env file not found at {env_path}. Attempting to load from environment variables only.")
                settings = Settings()
        
        logger.info(f"Settings loaded. Judge model: {settings.JUDGE_MODEL_NAME}, Max budget: ${settings.MAX_BUDGET_USD}")

    except ValidationError as ve:
        logger.error(f"Error loading settings: {ve}. Aborting run.")
        return
    except Exception as e: 
        logger.error(f"An unexpected error occurred during settings loading: {e}. Aborting run.", exc_info=True)
        return

    serializable_settings = settings.model_dump(exclude={'OPENROUTER_API_KEY'})
    write_meta_json(
        run_id=current_run_id,
        config_settings=serializable_settings,
        base_path_str=base_output_dir_str
    )

    router_client: Optional[RouterClient] = None
    db_conn: Optional[sqlite3.Connection] = None

    try:
        router_client = RouterClient(settings)

        db_file = str(run_output_path / f"{current_run_id}_benchmark_data.sqlite")
        db_conn = create_connection(db_file)
        if not db_conn or not execute_ddl(db_conn):
            logger.error("Failed to initialize SQLite database. Aborting run.")
            return

        if not models_to_run:
            models_to_run = ["mistralai/mistral-7b-instruct"]
            logger.info(f"No models specified, using default: {models_to_run}")

        judge_prompt_template_content = load_judge_prompt_template()
        judge_llm_name = settings.JUDGE_MODEL_NAME

        logger.info(f"--- Starting Generation Phase for run {current_run_id} ---")
        for model_name in models_to_run:
            logger.info(f"Running generations for model: {model_name} ({num_runs_per_model} runs)")
            try:
                await run_generations_for_model(
                    router_client=router_client,
                    model=model_name,
                    num_runs=num_runs_per_model,
                    current_run_id=current_run_id,
                    base_output_dir=base_output_dir_str
                )
            except BudgetExceededError as be:
                logger.error(f"Budget exceeded during generation for model {model_name}: {be}. Stopping further generations.")
                break 
            except Exception as e:
                logger.error(f"Error during generation for model {model_name}: {e}", exc_info=True)
        logger.info(f"--- Generation Phase Complete for run {current_run_id} ---")

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

                    generation_result_obj = GenerationResult(**gen_data_dict)
                    processed_files_count += 1

                    logger.info(f"Judging result for {generation_result_obj.model} run {generation_result_obj.run}")
                    judge_score_obj = await judge_response( 
                        router_client=router_client,
                        generation_result=generation_result_obj,
                        judge_model_name=judge_llm_name,
                        judge_prompt_template=judge_prompt_template_content
                    )

                    if judge_score_obj:
                        # ---- MODIFICATION START ----
                        # Calculate the total score from the individual components
                        actual_total_score = (
                            judge_score_obj.phonetische_aehnlichkeit +
                            judge_score_obj.anzueglichkeit +
                            judge_score_obj.logik +
                            judge_score_obj.kreativitaet
                        )
                        # Update the gesamt score in the judge_score_obj
                        # The Pydantic model's validator for 'gesamt' will clamp this sum if necessary.
                        judge_score_obj.gesamt = actual_total_score
                        logger.info(f"Calculated total score for {generation_result_obj.model} run {generation_result_obj.run}: {actual_total_score} (set to judge_score_obj.gesamt: {judge_score_obj.gesamt})")
                        # ---- MODIFICATION END ----

                        benchmark_record_obj = BenchmarkRecord(
                            generation=generation_result_obj, judge=judge_score_obj
                        )
                        save_benchmark_record( 
                            record=benchmark_record_obj,
                            run_id=current_run_id,
                            base_path_str=base_output_dir_str
                        )
                        if db_conn: 
                            insert_benchmark_record(db_conn, benchmark_record_obj, current_run_id) 
                        logger.info(f"Saved and stored judged record for {generation_result_obj.model} run {generation_result_obj.run}")
                        judged_records_count += 1
                    else:
                        logger.warning(
                            f"Judging skipped or failed for {generation_result_obj.model} "
                            f"run {generation_result_obj.run}. Raw file: {gen_file_path.name}"
                        )
                except json.JSONDecodeError as e:
                    logger.error(f"Error decoding JSON from {gen_file_path.name}: {e}")
                except ValidationError as e: 
                    logger.error(f"Data validation error for {gen_file_path.name}: {e}")
                except BudgetExceededError as be: 
                    logger.error(f"Budget exceeded during judging of file {gen_file_path.name}: {be}. Stopping further judging.")
                    break 
                except Exception as e:
                    logger.error(f"Error processing file {gen_file_path.name} for judging: {e}", exc_info=True)

            logger.info(f"Judging phase complete. Processed {processed_files_count} generated files. Created {judged_records_count} judged records.")

    except BudgetExceededError as be: 
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
    logger.info("Starting main.py test run using __main__ block.")

    Path("src/prompts").mkdir(parents=True, exist_ok=True)
    benchmark_prompt_path = Path("src/prompts/benchmark_prompt.md")
    judge_prompt_path = Path("src/prompts/judge_checklist.md")

    if not benchmark_prompt_path.exists() or benchmark_prompt_path.read_text(encoding="utf-8").strip() == "":
        benchmark_prompt_path.write_text(
            "Erzähl einen Witz über einen Informatiker und einen Physiker.\n"
            "Antworte im Stil eines Comedians und gib eine Zusammenfassung deiner Antwort in EXAKT diesem Format:\n"
            "### ZUSAMMENFASSUNG\n- Gewünscht: <Zusammenfassung Wunsch>\n- Bekommen: <Zusammenfassung Antwort>",
            encoding="utf-8"
        )
        logger.info(f"Created dummy benchmark prompt at {benchmark_prompt_path}")

    if not judge_prompt_path.exists() or judge_prompt_path.read_text(encoding="utf-8").strip() == "":
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

    test_run_id_main = f"main_test_run_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
    test_models = ["mistralai/mistral-7b-instruct"] 

    try:
        asyncio.run(run_benchmark(
            run_id=test_run_id_main,
            models_to_run=test_models,
            num_runs_per_model=2, 
            base_output_dir_str="benchmarks_main_output" 
        ))
    except Exception as e:
        logger.critical(f"Error running benchmark from __main__: {e}", exc_info=True)
    finally:
        logger.info("Finished main.py test run from __main__ block.")