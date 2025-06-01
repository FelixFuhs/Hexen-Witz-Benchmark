import json
import csv
import logging
from pathlib import Path
from datetime import datetime, timezone 
from typing import Dict, Any

from src.models import GenerationResult, BenchmarkRecord
from src.config import Settings 

logger = logging.getLogger(__name__)

def ensure_dir_structure(run_id: str, base_path_str: str = "benchmarks") -> Path:
    """
    Ensures the necessary directory structure for a given run_id exists.
    <base_path>/<run_id>/raw
    <base_path>/<run_id>/judged
    """
    base_path = Path(base_path_str)
    run_path = base_path / run_id
    raw_path = run_path / "raw"
    judged_path = run_path / "judged"

    try:
        raw_path.mkdir(parents=True, exist_ok=True)
        judged_path.mkdir(parents=True, exist_ok=True)
        logger.info(f"Ensured directory structure for run_id {run_id} at {run_path}")
        return run_path
    except OSError as e:
        logger.error(f"Failed to create directory structure for {run_id} at {run_path}: {e}")
        raise 


def save_generation_result(result: GenerationResult, run_id: str, base_path_str: str = "benchmarks") -> None:
    """
    Saves a single GenerationResult to a JSON file in the raw directory.
    Also appends its cost to the cost_report.csv.
    """
    try:
        run_path = ensure_dir_structure(run_id, base_path_str)
    except OSError:
        logger.error(f"Cannot save GenerationResult for run_id {run_id} due to directory creation failure.")
        return

    raw_path = run_path / "raw"
    safe_model_name = result.model.replace('/', '_')
    file_name = f"{safe_model_name}_{result.run}.json" 
    file_path = raw_path / file_name

    try:
        with file_path.open("w", encoding="utf-8") as f:
            f.write(result.model_dump_json(indent=2))
        logger.info(f"Saved GenerationResult to {file_path}")

        _append_generation_cost_to_report(result, run_id, base_path_str)

    except IOError as e:
        logger.error(f"Failed to save GenerationResult to {file_path}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error saving GenerationResult to {file_path}: {e}", exc_info=True)


def save_benchmark_record(record: BenchmarkRecord, run_id: str, base_path_str: str = "benchmarks") -> None:
    """Saves a single BenchmarkRecord to a JSON file in the judged directory."""
    try:
        run_path = ensure_dir_structure(run_id, base_path_str)
    except OSError:
        logger.error(f"Cannot save BenchmarkRecord for run_id {run_id} due to directory creation failure.")
        return

    judged_path = run_path / "judged"
    safe_model_name = record.generation.model.replace('/', '_')
    file_name = f"{safe_model_name}_{record.generation.run}.json" 
    file_path = judged_path / file_name

    try:
        with file_path.open("w", encoding="utf-8") as f:
            f.write(record.model_dump_json(indent=2))
        logger.info(f"Saved BenchmarkRecord to {file_path}")
    except IOError as e:
        logger.error(f"Failed to save BenchmarkRecord to {file_path}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error saving BenchmarkRecord to {file_path}: {e}", exc_info=True)


def _append_generation_cost_to_report(
    result: GenerationResult, run_id: str, base_path_str: str = "benchmarks"
) -> None:
    """
    Appends cost information from a GenerationResult to the cost_report.csv for the run.
    This is an internal helper called by save_generation_result.
    """
    try:
        run_path = Path(base_path_str) / run_id
        if not run_path.exists(): 
             logger.warning(f"Run path {run_path} does not exist for cost report. Attempting to create.")
             ensure_dir_structure(run_id, base_path_str)

    except OSError: 
        logger.error(f"Cannot append to cost report for run_id {run_id} due to directory issue.")
        return


    report_path = run_path / "cost_report.csv"
    file_exists = report_path.exists()

    try:
        with report_path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            if not file_exists:
                writer.writerow(["timestamp", "run_id", "model", "run_num", "cost_usd", "prompt_tokens", "completion_tokens"])
            writer.writerow([
                result.timestamp.isoformat(),
                run_id,
                result.model,
                result.run,
                f"{result.cost_usd:.8f}", 
                result.prompt_tokens,
                result.completion_tokens
            ])
    except IOError as e:
        logger.error(f"Failed to append to cost report {report_path}: {e}")
    except Exception as e:
        logger.error(f"Unexpected error appending to cost report {report_path}: {e}", exc_info=True)


def write_meta_json(
    run_id: str, config_settings: Dict[str, Any], base_path_str: str = "benchmarks"
) -> None:
    """Writes a meta.json file for the run, including run_id and configuration settings."""
    try:
        run_path = ensure_dir_structure(run_id, base_path_str)
    except OSError:
        logger.error(f"Cannot write meta.json for run_id {run_id} due to directory creation failure.")
        return

    meta_path = run_path / "meta.json"

    serializable_config = {}
    for k, v in config_settings.items():
        if hasattr(v, 'model_dump'): 
            serializable_config[k] = v.model_dump()
        elif isinstance(v, (str, int, float, bool, list, dict, type(None))):
            serializable_config[k] = v
        else:
            try:
                serializable_config[k] = str(v)
                logger.warning(f"Configuration value for key '{k}' was converted to string for meta.json serialization.")
            except Exception:
                logger.error(f"Configuration value for key '{k}' is not JSON serializable and could not be converted to string.")
                serializable_config[k] = "NOT_SERIALIZABLE"


    data_to_write = {
        "run_id": run_id,
        "creation_timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "config_settings": serializable_config,
    }

    try:
        with meta_path.open("w", encoding="utf-8") as f:
            json.dump(data_to_write, f, indent=2)
        logger.info(f"Saved meta.json to {meta_path}")
    except IOError as e:
        logger.error(f"Failed to save meta.json to {meta_path}: {e}")
    except TypeError as e: 
        logger.error(f"Failed to serialize data for meta.json: {e}. Data: {data_to_write}", exc_info=True)
    except Exception as e:
        logger.error(f"Unexpected error saving meta.json to {meta_path}: {e}", exc_info=True)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    test_run_id = f"test_run_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"

    sample_gen_result = GenerationResult(
        model="test_model/v1",
        run=1,
        summary=None, 
        full_response="This is a test response.",
        prompt_tokens=10,
        completion_tokens=5,
        cost_usd=0.000123,
        timestamp=datetime.now(timezone.utc)
    )
    save_generation_result(sample_gen_result, test_run_id)

    sample_gen_result_run2 = GenerationResult(
        model="another_model/v2",
        run=2, 
        summary=None,
        full_response="Another test response.",
        prompt_tokens=15,
        completion_tokens=8,
        cost_usd=0.000456,
        timestamp=datetime.now(timezone.utc)
    )
    save_generation_result(sample_gen_result_run2, test_run_id)

    from src.models import JudgeScore, Summary 
    sample_judge_score = JudgeScore(
        phonetische_aehnlichkeit=10,
        anzueglichkeit=5,
        logik=10,
        kreativitaet=10,
        gesamt=35,
        begruendung={"test": "good"},
        flags=[]
    )
    sample_benchmark_record = BenchmarkRecord(
        generation=sample_gen_result, 
        judge=sample_judge_score
    )
    save_benchmark_record(sample_benchmark_record, test_run_id)

    class DummyNonSerializable:
        pass

    sample_config = {
        "llm_model": "test_model/v1",
        "num_runs": 10,
        "temperature": 0.7,
        "judge_llm": "judge_model/v1",
        "max_budget": 100.0,
        "complex_setting": Settings(OPENROUTER_API_KEY="dummy", MAX_BUDGET_USD=50.0), 
        "non_serializable_item": DummyNonSerializable() 
    }
    write_meta_json(test_run_id, sample_config)

    print(f"Test files generated in benchmarks/{test_run_id}")
    print(f"Check benchmarks/{test_run_id}/raw/ for generation results.")
    print(f"Check benchmarks/{test_run_id}/judged/ for benchmark records.")
    print(f"Check benchmarks/{test_run_id}/cost_report.csv for cost details.")
    print(f"Check benchmarks/{test_run_id}/meta.json for run metadata.")