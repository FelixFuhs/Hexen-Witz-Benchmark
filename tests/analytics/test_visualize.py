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
    generate_standard_visualizations
)
# from src.storage.database import create_connection as create_real_db_conn, execute_ddl # For setting up test DB

# Tests for analytics/visualize.py will be implemented here.

@pytest.fixture
def temp_run_dir(tmp_path: Path) -> Path:
    """Creates a temporary run directory structure for visualization tests."""
    run_id = "vis_test_run_001"
    base_dir = tmp_path / "benchmarks_output_vis_test"
    run_dir = base_dir / run_id
    # visualize.py expects plots dir to be created by save_figure,
    # and DB/CSV to exist.
    run_dir.mkdir(parents=True, exist_ok=True)
    return run_dir

@pytest.fixture
def dummy_db_path(temp_run_dir: Path) -> str:
    """Creates a dummy SQLite DB with some data for testing."""
    db_file = temp_run_dir / f"{temp_run_dir.name}_benchmark_data.sqlite"
    conn = sqlite3.connect(str(db_file))
    cursor = conn.cursor()
    # Simplified DDL for test purposes if not using the full DDL from storage.database
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS records (
      id TEXT PRIMARY KEY, run_id TEXT, model TEXT, run INTEGER, gewuenscht TEXT, bekommen TEXT,
      phonetische_aehnlichkeit INTEGER, anzueglichkeit INTEGER, logik INTEGER, kreativitaet INTEGER, gesamt INTEGER,
      prompt_tokens INTEGER, completion_tokens INTEGER, cost_usd REAL, ts TIMESTAMP
    );""")
    # Insert sample data
    sample_data = [
        ("rec1", temp_run_dir.name, "modelA", 1, "gw1", "gb1", 10, 5, 5, 5, 25, 10, 10, 0.01, "2023-01-01T12:00:00Z"),
        ("rec2", temp_run_dir.name, "modelA", 2, "gw2", "gb2", 12, 6, 6, 6, 30, 12, 12, 0.012, "2023-01-01T12:05:00Z"),
        ("rec3", temp_run_dir.name, "modelB", 1, "gw3", "gb3", 15, 7, 7, 7, 36, 15, 15, 0.015, "2023-01-01T12:10:00Z"),
    ]
    cursor.executemany("INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", sample_data)
    conn.commit()
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
