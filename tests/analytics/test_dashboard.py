import pytest
from pathlib import Path
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

# Note: Full testing of Streamlit apps often involves UI interaction simulation,
# which can be done with tools like Selenium or Playwright for end-to-end tests,
# or Streamlit's own AppTest for more unit/integration style testing of the app's Python logic.
# For this phase, focusing on helper functions like get_available_run_ids is a good start.
# The main_dashboard() function in dashboard.py is the Streamlit app itself and would
# typically be tested via `streamlit run` and manual inspection or using AppTest.
