import pytest
import pandas as pd
import plotly.graph_objects as go
from pathlib import Path
import sqlite3 # For creating a dummy DB for tests

from src.analytics.visualize import (
    _get_db_connection,
    _fetch_data_from_db,
    create_scores_boxplot,
    create_cost_plot,
    save_figure,
    generate_standard_visualizations,
    fetch_all_run_data,
    calculate_global_leaderboard
)
from src.storage.database import (
    create_connection as create_db_conn_actual, # Renamed to avoid conflict if any local create_connection
    execute_ddl,
    insert_benchmark_record
)
from src.models import BenchmarkRecord, GenerationResult, Summary, JudgeScore
from datetime import datetime, timezone
import shutil
import logging
import unittest.mock as mock # For patching logging

# Tests for analytics/visualize.py will be implemented here.

# --- Helper to create BenchmarkRecord instances ---
def _create_sample_record(model_name: str, run_num: int, gesamt_score: int, record_ts: Optional[datetime] = None) -> BenchmarkRecord:
    """Creates a sample BenchmarkRecord for testing."""
    if record_ts is None:
        record_ts = datetime.now(timezone.utc)

    summary = Summary(gewuenscht="Test gewuenscht", bekommen="Test bekommen")
    generation = GenerationResult(
        model=model_name,
        run=run_num,
        summary=summary,
        full_response="Full response here",
        prompt_tokens=10,
        completion_tokens=20,
        cost_usd=0.001,
        timestamp=record_ts
    )
    judge = JudgeScore(
        phonetische_aehnlichkeit=gesamt_score // 3, # Dummy distribution
        anzueglichkeit=0,
        logik=gesamt_score // 3,
        kreativitaet=gesamt_score // 3,
        gesamt=gesamt_score,
        begruendung={},
        flags=[]
    )
    return BenchmarkRecord(generation=generation, judge=judge)


# --- Fixtures for FetchAllRunData ---

@pytest.fixture
def benchmark_base_dir(tmp_path_factory):
    """Creates a temporary base directory for benchmark runs for a single test."""
    base_dir = tmp_path_factory.mktemp("benchmark_runs")
    yield base_dir
    # shutil.rmtree(base_dir) # tmp_path_factory handles cleanup

def _setup_mock_run_environment(base_dir: Path, run_id: str, records_to_insert: List[BenchmarkRecord] = None,
                                create_db: bool = True, create_records_table: bool = True):
    """
    Helper to set up a single mock run environment.
    Creates run directory, DB, table, and inserts records.
    """
    run_path = base_dir / run_id
    run_path.mkdir(parents=True, exist_ok=True)
    db_path_str = str(run_path / f"{run_id}_benchmark_data.sqlite")

    if not create_db:
        return run_path # Return run_path, DB doesn't exist

    conn = create_db_conn_actual(db_path_str)
    assert conn is not None, f"Failed to create DB connection for {run_id}"

    if create_records_table:
        assert execute_ddl(conn), f"Failed to execute DDL for {run_id}"

    if records_to_insert:
        for record in records_to_insert:
            assert insert_benchmark_record(conn, record, run_id), \
                   f"Failed to insert record for {run_id}, model {record.generation.model}"
    conn.close()
    return run_path


# --- Tests for fetch_all_run_data ---

class TestFetchAllRunData:

    def test_fetch_all_data_happy_path(self, benchmark_base_dir):
        run1_id = "run_001"
        run1_records = [
            _create_sample_record("model_X", 1, 10),
            _create_sample_record("model_Y", 1, 20)
        ]
        _setup_mock_run_environment(benchmark_base_dir, run1_id, run1_records)

        run2_id = "run_002"
        run2_records = [
            _create_sample_record("model_X", 2, 12), # Note: model_X also in run_001
            _create_sample_record("model_Z", 1, 30)
        ]
        _setup_mock_run_environment(benchmark_base_dir, run2_id, run2_records)

        available_runs = [
            (run1_id, str(benchmark_base_dir / run1_id)),
            (run2_id, str(benchmark_base_dir / run2_id))
        ]

        combined_df = fetch_all_run_data(available_runs)

        assert not combined_df.empty
        assert len(combined_df) == 4 # 2 from run1 + 2 from run2
        assert "model_X" in combined_df["model"].values
        assert "model_Y" in combined_df["model"].values
        assert "model_Z" in combined_df["model"].values
        assert "run_001" in combined_df["run_id"].values
        assert "run_002" in combined_df["run_id"].values
        # Check specific scores to be more robust
        assert combined_df[combined_df["model"] == "model_X"]["gesamt"].sum() == 22 # 10 + 12

    def test_fetch_all_data_one_run_empty_table(self, benchmark_base_dir):
        run1_id = "run_001"
        run1_records = [_create_sample_record("model_A", 1, 15)]
        _setup_mock_run_environment(benchmark_base_dir, run1_id, run1_records)

        run2_id = "run_002_empty" # DB and table exist, but no records
        _setup_mock_run_environment(benchmark_base_dir, run2_id, records_to_insert=[])

        available_runs = [
            (run1_id, str(benchmark_base_dir / run1_id)),
            (run2_id, str(benchmark_base_dir / run2_id))
        ]
        combined_df = fetch_all_run_data(available_runs)

        assert not combined_df.empty
        assert len(combined_df) == 1
        assert combined_df.iloc[0]["model"] == "model_A"
        assert combined_df.iloc[0]["gesamt"] == 15

    def test_fetch_all_data_db_not_found(self, benchmark_base_dir, caplog):
        run1_id = "run_001_valid"
        run1_records = [_create_sample_record("model_B", 1, 25)]
        _setup_mock_run_environment(benchmark_base_dir, run1_id, run1_records)

        run2_id_no_db = "run_002_no_db"
        # Setup run_002_no_db directory, but don't create a DB file inside it
        _setup_mock_run_environment(benchmark_base_dir, run2_id_no_db, create_db=False)

        available_runs = [
            (run1_id, str(benchmark_base_dir / run1_id)),
            (run2_id_no_db, str(benchmark_base_dir / run2_id_no_db))
        ]

        with mock.patch("src.analytics.visualize.logger") as mock_logger:
            combined_df = fetch_all_run_data(available_runs)

        assert not combined_df.empty
        assert len(combined_df) == 1
        assert combined_df.iloc[0]["model"] == "model_B"
        # Check that an error was logged for the missing DB
        # src.analytics.visualize._get_db_connection logs an error
        # src.analytics.visualize.fetch_all_run_data also logs an error if conn is None
        assert any("Failed to get DB connection for run run_002_no_db" in message for message in caplog.messages if "ERROR" in message)


    def test_fetch_all_data_one_run_no_records_table(self, benchmark_base_dir, caplog):
        run1_id = "run_001_valid"
        run1_records = [_create_sample_record("model_C", 1, 35)]
        _setup_mock_run_environment(benchmark_base_dir, run1_id, run1_records)

        run2_id_no_table = "run_002_no_table"
        _setup_mock_run_environment(benchmark_base_dir, run2_id_no_table, create_records_table=False)

        available_runs = [
            (run1_id, str(benchmark_base_dir / run1_id)),
            (run2_id_no_table, str(benchmark_base_dir / run2_id_no_table))
        ]
        combined_df = fetch_all_run_data(available_runs)

        assert not combined_df.empty
        assert len(combined_df) == 1
        assert combined_df.iloc[0]["model"] == "model_C"
        # Check logs: _fetch_data_from_db should log an error about the table not existing
        assert any("Error fetching data from 'records' table" in message for message in caplog.messages if "ERROR" in message)
        assert any(f"no such table: records" in message.lower() for message in caplog.messages if "ERROR" in message)


    def test_fetch_all_data_no_valid_runs(self, benchmark_base_dir, caplog):
        run1_id_no_db = "run_001_no_db"
        _setup_mock_run_environment(benchmark_base_dir, run1_id_no_db, create_db=False)

        run2_id_no_table = "run_002_no_table"
        _setup_mock_run_environment(benchmark_base_dir, run2_id_no_table, create_records_table=False)

        available_runs = [
            (run1_id_no_db, str(benchmark_base_dir / run1_id_no_db)),
            (run2_id_no_table, str(benchmark_base_dir / run2_id_no_table))
        ]
        combined_df = fetch_all_run_data(available_runs)
        assert combined_df.empty
        # Check logs for both issues
        assert any("Failed to get DB connection for run run_001_no_db" in message for message in caplog.messages if "ERROR" in message)
        assert any("Error fetching data from 'records' table" in message for message in caplog.messages if "ERROR" in message)

    def test_fetch_all_data_empty_input_list(self):
        combined_df = fetch_all_run_data([])
        assert combined_df.empty

# --- Tests for calculate_global_leaderboard ---

class TestCalculateGlobalLeaderboard:

    def test_calculate_leaderboard_happy_path(self):
        data = {
            'model': ['model_A', 'model_B', 'model_A', 'model_C', 'model_B'],
            'gesamt': [10, 20, 12, 30, 22],
            'run_id': ['r1', 'r1', 'r2', 'r2', 'r3'] # Other columns should be ignored
        }
        input_df = pd.DataFrame(data)
        leaderboard = calculate_global_leaderboard(input_df)

        assert not leaderboard.empty
        assert list(leaderboard.columns) == ['model', 'average_gesamt_score']
        assert len(leaderboard) == 3

        # Expected: model_C: 30, model_B: 21, model_A: 11
        assert leaderboard.iloc[0]['model'] == 'model_C'
        assert leaderboard.iloc[0]['average_gesamt_score'] == 30.0
        assert leaderboard.iloc[1]['model'] == 'model_B'
        assert leaderboard.iloc[1]['average_gesamt_score'] == 21.0
        assert leaderboard.iloc[2]['model'] == 'model_A'
        assert leaderboard.iloc[2]['average_gesamt_score'] == 11.0

    def test_calculate_leaderboard_empty_input(self):
        input_df = pd.DataFrame(columns=['model', 'gesamt'])
        leaderboard = calculate_global_leaderboard(input_df)
        assert leaderboard.empty

    def test_calculate_leaderboard_missing_model_column(self, caplog):
        data = {'gesamt': [10, 20]}
        input_df = pd.DataFrame(data)
        leaderboard = calculate_global_leaderboard(input_df)
        assert leaderboard.empty
        assert any("Required columns missing" in message for message in caplog.messages if "ERROR" in message)

    def test_calculate_leaderboard_missing_gesamt_column(self, caplog):
        data = {'model': ['model_A', 'model_B']}
        input_df = pd.DataFrame(data)
        leaderboard = calculate_global_leaderboard(input_df)
        assert leaderboard.empty
        assert any("Required columns missing" in message for message in caplog.messages if "ERROR" in message)

    def test_calculate_leaderboard_with_nan_non_numeric_scores(self):
        data = {
            'model': ['model_A', 'model_A', 'model_A', 'model_B', 'model_B', 'model_C'],
            'gesamt': [10, None, 'invalid_score', 20, float('NaN'), 30.5]
        }
        input_df = pd.DataFrame(data)
        leaderboard = calculate_global_leaderboard(input_df)

        assert not leaderboard.empty
        # Expected: model_C: 30.5, model_B: 20.0, model_A: 10.0
        assert leaderboard.iloc[0]['model'] == 'model_C'
        assert leaderboard.iloc[0]['average_gesamt_score'] == 30.5
        assert leaderboard.iloc[1]['model'] == 'model_B'
        assert leaderboard.iloc[1]['average_gesamt_score'] == 20.0
        assert leaderboard.iloc[2]['model'] == 'model_A'
        assert leaderboard.iloc[2]['average_gesamt_score'] == 10.0
        assert len(leaderboard) == 3

    def test_calculate_leaderboard_all_nan_scores_for_a_model(self):
        data = {
            'model': ['model_A', 'model_A', 'model_B'],
            'gesamt': [None, 'invalid', 20]
        }
        input_df = pd.DataFrame(data)
        leaderboard = calculate_global_leaderboard(input_df)
        assert len(leaderboard) == 1
        assert leaderboard.iloc[0]['model'] == 'model_B'
        assert leaderboard.iloc[0]['average_gesamt_score'] == 20.0

    def test_calculate_leaderboard_no_valid_scores_at_all(self, caplog):
        data = {
            'model': ['model_A', 'model_A'],
            'gesamt': [None, 'invalid']
        }
        input_df = pd.DataFrame(data)
        leaderboard = calculate_global_leaderboard(input_df)
        assert leaderboard.empty
        assert any("No valid 'gesamt' scores available" in message for message in caplog.messages if "WARNING" in message)


    def test_calculate_leaderboard_single_model_multiple_entries(self):
        data = {
            'model': ['model_X', 'model_X', 'model_X'],
            'gesamt': [10, 15, 20]
        }
        input_df = pd.DataFrame(data)
        leaderboard = calculate_global_leaderboard(input_df)
        assert len(leaderboard) == 1
        assert leaderboard.iloc[0]['model'] == 'model_X'
        assert leaderboard.iloc[0]['average_gesamt_score'] == 15.0 # (10+15+20)/3

    def test_calculate_leaderboard_multiple_models_single_entries(self):
        data = {
            'model': ['model_P', 'model_Q', 'model_R'],
            'gesamt': [5, 25, 15]
        }
        input_df = pd.DataFrame(data)
        leaderboard = calculate_global_leaderboard(input_df)
        assert len(leaderboard) == 3
        # Expected: model_Q: 25, model_R: 15, model_P: 5
        assert leaderboard.iloc[0]['model'] == 'model_Q'
        assert leaderboard.iloc[0]['average_gesamt_score'] == 25.0
        assert leaderboard.iloc[1]['model'] == 'model_R'
        assert leaderboard.iloc[1]['average_gesamt_score'] == 15.0
        assert leaderboard.iloc[2]['model'] == 'model_P'
        assert leaderboard.iloc[2]['average_gesamt_score'] == 5.0


@pytest.fixture
# The existing fixtures temp_run_dir, dummy_db_path, dummy_cost_csv_path might need adjustment
# if they conflict or if the new benchmark_base_dir fixture is preferred for these tests.
# For now, keeping them separate. New tests use benchmark_base_dir.

@pytest.fixture
def temp_run_dir(tmp_path: Path) -> Path: # Existing fixture
    """Creates a temporary run directory structure for visualization tests."""
    run_id = "vis_test_run_001" # This is a fixed run_id
    base_dir = tmp_path / "benchmarks_output_vis_test" # Fixed base
    run_dir = base_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir

@pytest.fixture
def dummy_db_path(temp_run_dir: Path) -> str: # Existing fixture, uses the fixed run_id from temp_run_dir
    """Creates a dummy SQLite DB with some data for testing."""
    db_file = temp_run_dir / f"{temp_run_dir.name}_benchmark_data.sqlite" # temp_run_dir.name IS vis_test_run_001
    # conn = sqlite3.connect(str(db_file)) # Original
    conn = create_db_conn_actual(str(db_file)) # Use actual connection creator
    assert conn is not None

    # Use actual DDL execution
    ddl_executed = execute_ddl(conn)
    assert ddl_executed

    # Insert sample data using actual BenchmarkRecord and insert_benchmark_record
    # For simplicity, we'll adapt the old sample_data structure to BenchmarkRecord

    # Note: The original dummy_db_path manually created the 'records' table and inserted.
    # The new approach uses the application's DDL and insert logic.
    # This means the records must be instances of BenchmarkRecord.

    records_to_insert = [
        _create_sample_record(model_name="modelA", run_num=1, gesamt_score=25, record_ts=datetime.fromisoformat("2023-01-01T12:00:00Z")),
        _create_sample_record(model_name="modelA", run_num=2, gesamt_score=30, record_ts=datetime.fromisoformat("2023-01-01T12:05:00Z")),
        _create_sample_record(model_name="modelB", run_num=1, gesamt_score=36, record_ts=datetime.fromisoformat("2023-01-01T12:10:00Z")),
    ]

    for record in records_to_insert:
        # The run_id for insert_benchmark_record should match the DB's run context.
        # Here, temp_run_dir.name is 'vis_test_run_001'
        insert_success = insert_benchmark_record(conn, record, temp_run_dir.name)
        assert insert_success, f"Failed to insert record for model {record.generation.model}"

    conn.close()
    return str(db_file)

@pytest.fixture
def dummy_cost_csv_path(temp_run_dir: Path) -> str:
    """Creates a dummy cost_report.csv for testing."""
    csv_file = temp_run_dir / "cost_report.csv"
    header = ["timestamp", "run_id", "model", "run_num", "cost_usd", "prompt_tokens", "completion_tokens"]
    data = [
        ("2023-01-01T12:00:00Z", temp_run_dir.name, "modelA", 1, 0.01, 10, 10),
        ("2023-01-01T12:05:00Z", temp_run_dir.name, "modelA", 2, 0.012, 12, 12),
        ("2023-01-01T12:10:00Z", temp_run_dir.name, "modelB", 1, 0.015, 15, 15),
    ]
    df = pd.DataFrame(data, columns=header)
    df.to_csv(csv_file, index=False)
    return str(csv_file)

# Example test ideas for analytics/visualize.py:
# - test_get_db_connection_success_and_fail (read-only mode).
# - test_fetch_data_from_db_with_and_without_run_id.
# - test_create_scores_boxplot_valid_data_and_empty_data.
# - test_create_cost_plot_valid_data_and_empty_data.
# - test_save_figure_creates_html_and_png (mock fig.write_html/write_image).
# - test_generate_standard_visualizations_runs_through_and_calls_savers:
#   - Use dummy_db_path and dummy_cost_csv_path.
#   - Mock the plot creation functions to return a dummy figure.
#   - Mock save_figure to check it's called.

def test_get_db_connection(dummy_db_path: str):
    conn = _get_db_connection(dummy_db_path)
    assert conn is not None
    conn.close()

def test_fetch_data_from_db(dummy_db_path: str):
    conn = _get_db_connection(dummy_db_path)
    assert conn is not None
    run_id = Path(dummy_db_path).parent.name # Extract run_id from path
    df = _fetch_data_from_db(conn, run_id=run_id)
    conn.close()
    assert not df.empty
    assert len(df) == 3
    assert "modelA" in df["model"].values

def test_generate_standard_visualizations_smoke(dummy_db_path, dummy_cost_csv_path, mocker):
    """Smoke test to ensure generate_standard_visualizations runs without obvious errors."""
    run_id = Path(dummy_db_path).parent.name
    base_benchmark_dir = str(Path(dummy_db_path).parent.parent)

    # Mock save_figure to avoid actual file I/O and Kaleido dependency in this basic test
    mock_save = mocker.patch("src.analytics.visualize.save_figure")

    generate_standard_visualizations(run_id, base_benchmark_dir)

    # Check that save_figure was called for expected plots
    # (at least one for scores and one for costs if data is present)
    assert mock_save.call_count >= 2
    # Example: check if it was called with specific arguments for one plot
    # mock_save.assert_any_call(mocker.ANY, run_id, "scores_gesamt_boxplot", base_benchmark_dir)
    # mock_save.assert_any_call(mocker.ANY, run_id, "cost_per_model_barchart", base_benchmark_dir)
    # Note: mocker.ANY is used because the first argument is a plotly Figure object.

    # Verify that plot files would have been created in the correct "plots" subdirectory
    # by checking the path argument passed to save_figure (if needed, by inspecting call_args)
    # For example, the call_args_list for save_figure would contain:
    # call(fig_object, 'vis_test_run_001', 'scores_gesamt_boxplot', '/tmp/pytest-of-user/pytest-0/benchmarks_output_vis_test')
    # The last argument is base_benchmark_dir. save_figure constructs plots_output_path from this and run_id.
    # So, plots would be in /tmp/pytest-of-user/pytest-0/benchmarks_output_vis_test/vis_test_run_001/plots/
    # This can be checked more thoroughly if needed.
