import logging
import sqlite3
from pathlib import Path
from typing import List, Optional, Tuple

import streamlit as st
from src.analytics.visualize import (
    _get_db_connection,
    _fetch_data_from_db,
    create_scores_boxplot,
    create_cost_plot,
    fetch_all_run_data,
    calculate_global_leaderboard
)
import pandas as pd
import plotly.express as px

logger = logging.getLogger(__name__)

def get_available_run_ids(base_benchmark_dir_str: str = "benchmarks_output") -> List[Tuple[str, str]]:
    """
    Scans a directory for valid benchmark run IDs and their directory paths.
    A run is considered valid if it has a corresponding SQLite database
    and that database contains records for that run_id.
    Returns a list of tuples, where each tuple is (run_id, run_directory_path).
    """
    base_benchmark_dir = Path(base_benchmark_dir_str)
    if not base_benchmark_dir.exists() or not base_benchmark_dir.is_dir():
        logger.error(f"Base benchmark directory not found or is not a directory: {base_benchmark_dir_str}")
        return []

    available_runs_with_paths: List[Tuple[str, str]] = []
    potential_run_dirs = [d for d in base_benchmark_dir.iterdir() if d.is_dir() and d.name.startswith("run_")]

    for run_dir in potential_run_dirs:
        run_id = run_dir.name
        db_path = run_dir / f"{run_id}_benchmark_data.sqlite"

        if not db_path.exists() or not db_path.is_file():
            logger.warning(f"Database file not found for run {run_id} at {db_path}, skipping.")
            continue

        conn: Optional[sqlite3.Connection] = None
        try:
            conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            logger.debug(f"Successfully connected to database for run {run_id}: {db_path}")

            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM records WHERE run_id = ?", (run_id,))
            count_result = cursor.fetchone()

            if count_result is None:
                logger.warning(f"Query for record count returned None for run {run_id}, skipping.")
                continue

            count = count_result[0]
            if count > 0:
                logger.info(f"Run {run_id} has {count} records. Adding to available runs.")
                available_runs_with_paths.append((run_id, str(run_dir)))
            else:
                logger.info(f"Run {run_id} has no records in the database, skipping.")

        except sqlite3.Error as e:
            logger.error(f"SQLite error for run {run_id} with DB {db_path}: {e}. Skipping run.", exc_info=True)
            continue
        except Exception as e:
            logger.error(f"Unexpected error processing run {run_id} with DB {db_path}: {e}. Skipping run.", exc_info=True)
            continue
        finally:
            if conn:
                conn.close()
                logger.debug(f"Closed database connection for run {run_id}.")

    available_runs_with_paths.sort(key=lambda x: x[0], reverse=True)
    logger.info(f"Found available runs with paths: {available_runs_with_paths}")
    return available_runs_with_paths


def display_global_leaderboard(available_runs_with_paths: List[Tuple[str, str]]):
    """
    Fetches data from all runs, calculates a global leaderboard, and displays it.
    """
    st.header("Global Model Leaderboard")
    all_data_df = fetch_all_run_data(available_runs_with_paths)

    if all_data_df.empty:
        st.info("No data available from any benchmark runs to generate a global leaderboard.")
        return

    leaderboard_df = calculate_global_leaderboard(all_data_df)

    if leaderboard_df.empty:
        st.warning("Could not calculate the global leaderboard. Ensure there is valid 'gesamt' score data in the runs.")
        return

    # Create a horizontal bar chart for the leaderboard
    try:
        fig = px.bar(
            leaderboard_df,
            x='average_gesamt_score',
            y='model',
            orientation='h',
            title="Average 'Gesamt' Score Across All Runs",
            labels={'average_gesamt_score': "Average 'Gesamt' Score", 'model': 'Model'},
            text='average_gesamt_score' # Display score on bars
        )
        fig.update_traces(texttemplate='%{text:.2f}', textposition='outside') # Format text
        fig.update_layout(
            yaxis={'categoryorder': 'total ascending'}, # Highest score at the top
            xaxis_title="Average 'Gesamt' Score",
            yaxis_title="Model"
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        logger.error(f"Error generating leaderboard plot: {e}", exc_info=True)
        st.error("Could not generate the leaderboard visualization.")

    # Optionally, display the raw leaderboard data
    with st.expander("View Leaderboard Data Table"):
        st.dataframe(leaderboard_df)


def main_dashboard():
    st.set_page_config(page_title="Benchmark Analytics Dashboard", layout="wide")
    st.title("Benchmark Analytics Dashboard")

    base_benchmark_dir = "benchmarks_output" # Or allow configuration if needed

    available_runs_with_paths = get_available_run_ids(base_benchmark_dir)

    if not available_runs_with_paths:
        st.warning("No benchmark runs with analyzable data found. Please complete a benchmark run first.")
        return

    # Display Global Leaderboard first
    display_global_leaderboard(available_runs_with_paths)

    # Then, allow selection of individual runs
    st.sidebar.header("Individual Run Selection")
    selected_run_details = st.sidebar.selectbox(
        "Select a Benchmark Run:",
        options=available_runs_with_paths,
        format_func=lambda x: x[0], # Display only the run_id
        help="Only runs with data in their database are listed."
    )

    if selected_run_details:
        selected_run_id = selected_run_details[0]
        selected_run_path_str = selected_run_details[1]

        st.header(f"Results for Run: {selected_run_id}")

        # Construct paths using selected_run_path_str and selected_run_id
        db_path_str = str(Path(selected_run_path_str) / f"{selected_run_id}_benchmark_data.sqlite")
        cost_csv_path_str = str(Path(selected_run_path_str) / "cost_report.csv")

        conn = _get_db_connection(db_path_str)
        if conn:
            records_df = _fetch_data_from_db(conn, selected_run_id)
            # It's important to close the connection after fetching data
            try:
                conn.close()
                logger.debug(f"DB connection closed for run {selected_run_id} after fetching records.")
            except sqlite3.Error as e:
                logger.error(f"Error closing DB connection for run {selected_run_id}: {e}", exc_info=True)


            if not records_df.empty:
                st.subheader("Score Visualizations")
                col1, col2 = st.columns(2)
                with col1:
                    fig_boxplot_gesamt = create_scores_boxplot(
                        records_df, score_column='gesamt', title_prefix=""
                    )
                    if fig_boxplot_gesamt:
                        st.plotly_chart(fig_boxplot_gesamt, use_container_width=True)
                    else:
                        st.info("Could not generate 'Gesamt' score boxplot.")

                with col2:
                    fig_boxplot_phon = create_scores_boxplot(
                        records_df, score_column='phonetische_aehnlichkeit', title_prefix=""
                    )
                    if fig_boxplot_phon:
                        st.plotly_chart(fig_boxplot_phon, use_container_width=True)
                    else:
                        st.info("Could not generate 'Phonetische Ähnlichkeit' score boxplot.")
            else:
                # This case should ideally be prevented by get_available_run_ids
                st.error(f"The selected benchmark run '{selected_run_id}' contains no analyzable records in its database, despite being listed. This might indicate an issue.")

            # Cost plot
            cost_csv_file = Path(cost_csv_path_str)
            if cost_csv_file.exists():
                try:
                    cost_df = pd.read_csv(cost_csv_file)
                    if not cost_df.empty:
                        st.subheader("Cost Visualization")
                        fig_cost_per_model = create_cost_plot(cost_df, title_prefix="")
                        if fig_cost_per_model:
                            st.plotly_chart(fig_cost_per_model, use_container_width=True)
                        else:
                            st.info("Could not generate cost plot.")
                    else:
                        st.info(f"Cost report found for run '{selected_run_id}' but it is empty.")
                except pd.errors.EmptyDataError:
                    st.info(f"Cost report for run '{selected_run_id}' is empty (pandas EmptyDataError).")
                except Exception as e:
                    st.error(f"Failed to process cost report {cost_csv_path_str}: {e}")
            else:
                st.info(f"Cost report not found for run '{selected_run_id}' at {cost_csv_path_str}.")
        else:
            st.error(f"Failed to establish database connection for run '{selected_run_id}'.")
    else:
        # This case might occur if available_runs is populated but selectbox somehow returns None,
        # or if available_runs was empty to begin with (though that's handled above).
        # For clarity, ensure a message is shown if no run is actively selected.
        if available_runs_with_paths: # Only show this if there were runs to select from
            st.info("Please select a benchmark run from the sidebar to view results.")

if __name__ == "__main__":
    # Configure basic logging if running dashboard.py directly
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    main_dashboard()
