import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock
# For more advanced Streamlit testing, you might use:
# from streamlit.testing.v1 import AppTest

# For now, primarily testing helper functions if any, or basic app structure.
from src.analytics.dashboard import get_available_run_ids

# Tests for analytics/dashboard.py will be implemented here.

# Example test ideas for analytics/dashboard.py:
# - test_get_available_run_ids_empty_dir: Mock Path.iterdir to be empty.
# - test_get_available_run_ids_finds_valid_runs:
#   - Create dummy run directories with and without the required DB file.
#   - Check if only valid runs are returned.
# - test_get_available_run_ids_sorting: Check if runs are sorted (e.g. reverse chronologically if names are timestamps).

# More complex tests involving AppTest would simulate user interactions:
# - test_dashboard_loads_with_no_runs:
#   - `at = AppTest.from_file("src/analytics/dashboard.py")`
#   - `at.run()`
#   - `assert at.warning[0].value == "No benchmark runs found..."`
# - test_dashboard_selects_run_and_displays_data:
#   - Setup dummy run data.
#   - `at = AppTest.from_file("src/analytics/dashboard.py")`
#   - `at.run()`
#   - `at.sidebar.selectbox(key="Select a Benchmark Run:").select("your_dummy_run_id").run()`
#   - `assert at.header[0].value == "Results for Run: your_dummy_run_id"`
#   - `assert len(at.dataframe) > 0` (or check for specific metrics/plots)
# These AppTest examples require Streamlit >= 1.28 and careful setup.

@pytest.fixture
def temp_benchmark_output_dir(tmp_path: Path) -> Path:
    """Creates a temporary base directory for benchmark outputs for dashboard tests."""
    dashboard_test_output = tmp_path / "benchmarks_dashboard_test"
    dashboard_test_output.mkdir(parents=True, exist_ok=True)
    return dashboard_test_output

def test_get_available_run_ids_no_runs(temp_benchmark_output_dir: Path):
    runs = get_available_run_ids(str(temp_benchmark_output_dir))
    assert runs == []

def test_get_available_run_ids_with_valid_and_invalid_runs(temp_benchmark_output_dir: Path):
    run1_name = "run_20230101_120000"
    run2_name = "run_20230102_120000"
    invalid_run_name = "run_invalid_no_db"
    not_a_run_file = "some_file.txt"

    run1_path = temp_benchmark_output_dir / run1_name
    run1_path.mkdir()
    (run1_path / f"{run1_name}_benchmark_data.sqlite").touch() # Valid run

    run2_path = temp_benchmark_output_dir / run2_name
    run2_path.mkdir()
    (run2_path / f"{run2_name}_benchmark_data.sqlite").touch() # Valid run

    invalid_run_path = temp_benchmark_output_dir / invalid_run_name
    invalid_run_path.mkdir() # Invalid, no DB file

    (temp_benchmark_output_dir / not_a_run_file).touch() # Should be ignored

    runs = get_available_run_ids(str(temp_benchmark_output_dir))

    assert len(runs) == 2
    # Sorted reverse, so run2 (more recent) should be first
    assert runs == [run2_name, run1_name]
    assert invalid_run_name not in runs

def test_get_available_run_ids_base_dir_not_exists():
    runs = get_available_run_ids("non_existent_base_directory")
    assert runs == []

@patch('sqlite3.connect')
def test_get_available_run_ids_with_empty_db_records(mock_sqlite_connect, temp_benchmark_output_dir: Path):
    """
    Tests that get_available_run_ids filters out runs where the database
    indicates zero records for that specific run_id.
    """
    run_valid_data_name = "run_20230103_100000"
    run_valid_data_path = temp_benchmark_output_dir / run_valid_data_name
    run_valid_data_path.mkdir()
    valid_db_file_path = run_valid_data_path / f"{run_valid_data_name}_benchmark_data.sqlite"
    valid_db_file_path.touch()

    run_empty_records_name = "run_20230103_110000"
    run_empty_records_path = temp_benchmark_output_dir / run_empty_records_name
    run_empty_records_path.mkdir()
    empty_db_file_path = run_empty_records_path / f"{run_empty_records_name}_benchmark_data.sqlite"
    empty_db_file_path.touch()

    # Mocking the database connection and query results
    def mock_connect_side_effect(db_uri_str, uri):
        # Extract file path from 'file:path?mode=ro'
        db_path_str = db_uri_str.replace("file:", "").split("?")[0]

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value = mock_cursor
        mock_conn.close = MagicMock() # Mock the close method as it's called in finally

        if run_valid_data_name in db_path_str:
            # Simulate this run having 5 records
            mock_cursor.fetchone.return_value = (5,)
            logger_msg = f"Mocking connect for {db_path_str}: returning 5 records."
        elif run_empty_records_name in db_path_str:
            # Simulate this run having 0 records
            mock_cursor.fetchone.return_value = (0,)
            logger_msg = f"Mocking connect for {db_path_str}: returning 0 records."
        else:
            # Default for any other unexpected calls, though test should control this
            mock_cursor.fetchone.return_value = (0,)
            logger_msg = f"Mocking connect for {db_path_str}: returning default 0 records (unexpected)."

        # To aid debugging tests, you could print this:
        # print(logger_msg)
        return mock_conn

    mock_sqlite_connect.side_effect = mock_connect_side_effect

    # Call the function under test
    # Note: get_available_run_ids sorts in reverse, so run_empty_records_name would be first if not filtered
    runs = get_available_run_ids(str(temp_benchmark_output_dir))

    # Assertions
    assert run_valid_data_name in runs, f"Expected '{run_valid_data_name}' to be in runs."
    assert run_empty_records_name not in runs, f"Expected '{run_empty_records_name}' NOT to be in runs."
    assert len(runs) == 1, f"Expected 1 run, but got {len(runs)}: {runs}"

    # Verify that sqlite3.connect was called for both DBs
    # The str() conversion is important as Path objects might not match exactly if not careful
    mock_sqlite_connect.assert_any_call(f"file:{str(valid_db_file_path)}?mode=ro", uri=True)
    mock_sqlite_connect.assert_any_call(f"file:{str(empty_db_file_path)}?mode=ro", uri=True)

    # Check that execute was called on the cursor for each connection
    # This is a bit more involved as mock_conn is created inside side_effect
    # We can check call counts or inspect call_args_list on mock_sqlite_connect.return_value.cursor.return_value.execute
    # For simplicity here, we'll trust the side_effect correctly configured fetchone based on the DB.
    # A more rigorous check could be:
    # for call_obj in mock_sqlite_connect.call_args_list:
    #     args, kwargs = call_obj
    #     db_uri_passed = args[0]
    #     mock_connection_instance = mock_sqlite_connect.side_effect(db_uri_passed, uri=True) # re-invoke to get the mock_conn
    #     # Check if execute was called with the correct run_id
    #     if run_valid_data_name in db_uri_passed:
    #         mock_connection_instance.cursor().execute.assert_called_with("SELECT COUNT(*) FROM records WHERE run_id = ?", (run_valid_data_name,))
    #     elif run_empty_records_name in db_uri_passed:
    #         mock_connection_instance.cursor().execute.assert_called_with("SELECT COUNT(*) FROM records WHERE run_id = ?", (run_empty_records_name,))


# Note: Full testing of Streamlit apps often involves UI interaction simulation,
# which can be done with tools like Selenium or Playwright for end-to-end tests,
# or Streamlit's own AppTest for more unit/integration style testing of the app's Python logic.
# For this phase, focusing on helper functions like get_available_run_ids is a good start.
# The main_dashboard() function in dashboard.py is the Streamlit app itself and would
# typically be tested via `streamlit run` and manual inspection or using AppTest.
