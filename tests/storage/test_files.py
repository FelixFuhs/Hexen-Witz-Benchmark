import pytest
from pathlib import Path
import csv
import json
from datetime import datetime, timezone
from src.storage.files import (
    ensure_dir_structure,
    save_generation_result,
    save_benchmark_record,
    # _append_generation_cost_to_report, # Tested via save_generation_result
    write_meta_json
)
from src.models import GenerationResult, BenchmarkRecord, Summary, JudgeScore
from src.config import Settings # For sample config in meta.json test

# Tests for storage/files.py will be implemented here.

# Pytest fixture for a temporary base path for benchmark outputs
@pytest.fixture
def temp_benchmark_base_path(tmp_path: Path) -> Path:
    """Creates a temporary base directory for benchmark outputs."""
    return tmp_path / "benchmarks_test_output"

# Pytest fixture for a sample GenerationResult
@pytest.fixture
def sample_generation_result() -> GenerationResult:
    return GenerationResult(
        model="test_vendor/test_model_v1",
        run=1,
        summary=Summary(gewuenscht="Wunsch", bekommen="Bekommen"),
        full_response="Full response text here.",
        prompt_tokens=50,
        completion_tokens=150,
        cost_usd=0.00025,
        timestamp=datetime.now(timezone.utc)
    )

# Pytest fixture for a sample BenchmarkRecord
@pytest.fixture
def sample_benchmark_record(sample_generation_result: GenerationResult) -> BenchmarkRecord:
    judge_score = JudgeScore(
        phonetische_aehnlichkeit=30,
        anzueglichkeit=10,
        logik=15,
        kreativitaet=20,
        gesamt=75,
        begruendung={"overall": "Good job!"},
        flags=[]
    )
    return BenchmarkRecord(generation=sample_generation_result, judge=judge_score)

# Example test ideas for storage/files.py:
# - test_ensure_dir_structure_creates_dirs: Check if raw and judged dirs are made.
# - test_save_generation_result_creates_file_and_cost_report:
#   - Check if JSON file is created in raw dir with correct content.
#   - Check if cost_report.csv is created/appended with correct data.
# - test_save_benchmark_record_creates_file: Check if JSON file is created in judged dir.
# - test_write_meta_json_creates_file: Check if meta.json is created with correct content.
# - test_filename_sanitization: Ensure model names with '/' are saved correctly.
# - test_error_handling_io_error: Mock open() to raise IOError and check logging.
# - test_cost_report_appending: Call save_generation_result multiple times and check CSV.
# - test_meta_json_serialization_of_settings: Provide a Settings object and check serialization.

# Example test structure for ensure_dir_structure
def test_ensure_dir_structure(temp_benchmark_base_path: Path):
    run_id = "test_run_ensure"
    run_path = ensure_dir_structure(run_id, str(temp_benchmark_base_path))

    assert run_path == temp_benchmark_base_path / run_id
    assert (run_path / "raw").exists()
    assert (run_path / "raw").is_dir()
    assert (run_path / "judged").exists()
    assert (run_path / "judged").is_dir()

# Example test for save_generation_result (partial, more checks needed)
def test_save_generation_result(temp_benchmark_base_path: Path, sample_generation_result: GenerationResult):
    run_id = "test_run_save_gen"
    save_generation_result(sample_generation_result, run_id, str(temp_benchmark_base_path))

    expected_model_name_part = sample_generation_result.model.replace('/', '_')
    expected_file_name = f"{expected_model_name_part}_{sample_generation_result.run}.json"
    expected_file_path = temp_benchmark_base_path / run_id / "raw" / expected_file_name

    assert expected_file_path.exists()
    with expected_file_path.open("r") as f:
        data = json.load(f)
        assert data["model"] == sample_generation_result.model
        assert data["run"] == sample_generation_result.run

    cost_report_path = temp_benchmark_base_path / run_id / "cost_report.csv"
    assert cost_report_path.exists()
    with cost_report_path.open("r") as f:
        reader = csv.reader(f)
        header = next(reader)
        assert header == ["timestamp", "run_id", "model", "run_num", "cost_usd", "prompt_tokens", "completion_tokens"]
        row = next(reader)
        assert row[1] == run_id
        assert row[2] == sample_generation_result.model
        assert float(row[4]) == sample_generation_result.cost_usd
