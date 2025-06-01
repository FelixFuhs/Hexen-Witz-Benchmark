import streamlit as st
from pathlib import Path
import logging
import pandas as pd
import sqlite3 # Keep for type hinting Optional[sqlite3.Connection]
from typing import List, Optional

# Assuming src.analytics.visualize has the necessary functions
from src.analytics import visualize
# If _get_db_connection and _fetch_data_from_db are specific to visualize and not general storage helpers,
# it's fine to use them via visualize module.

# Setup Logger
# Streamlit apps often manage their own logging, but it's good practice for modules.
# However, direct Streamlit pages usually don't need a module-level logger like this
# unless there's complex non-UI logic within them. For now, this is fine.
logger = logging.getLogger(__name__)
# Basic logging config for when this module's functions might be called outside Streamlit context
# or for debugging. Streamlit's own logging might override or supplement this when run via `streamlit run`.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')


def get_available_run_ids(base_benchmark_dir_str: str = "benchmarks_output") -> List[str]:
    """
    Scans the base benchmark directory for available run_ids.
    A directory is considered a valid run if it contains the expected SQLite DB file.
    """
    base_path = Path(base_benchmark_dir_str)
    if not base_path.exists() or not base_path.is_dir():
        logger.warning(f"Base benchmark directory '{base_benchmark_dir_str}' not found or not a directory.")
        return []

    available_runs = []
    for d in base_path.iterdir():
        if d.is_dir():
            # Check for the presence of the SQLite DB file to qualify as a run directory
            db_file = d / f"{d.name}_benchmark_data.sqlite"
            if db_file.exists() and db_file.is_file():
                available_runs.append(d.name)
            else:
                logger.debug(f"Directory {d.name} skipped, missing DB file {db_file.name}")

    return sorted(available_runs, reverse=True) # Show most recent (if timestamped naming) first


def create_leaderboard_df(records_df: pd.DataFrame) -> pd.DataFrame:
    """
    Creates a leaderboard DataFrame from the records_df, summarizing model performance.

    Args:
        records_df: DataFrame containing benchmark records with 'model', 'gesamt',
                    and optionally 'phonetische_aehnlichkeit' columns.

    Returns:
        A pandas DataFrame for the leaderboard, sorted by 'Average Gesamt Score',
        or an empty DataFrame if input is invalid, has missing required columns, or any error occurs.
    """
    if records_df.empty:
        return pd.DataFrame()

    required_cols = ['model', 'gesamt']
    if not all(col in records_df.columns for col in required_cols):
        return pd.DataFrame()

    try:
        leaderboard_df = records_df.groupby('model').agg(
            num_runs=('model', 'count'),
            avg_gesamt_score=('gesamt', 'mean')
        )

        if 'phonetische_aehnlichkeit' in records_df.columns:
            phon_avg_series = records_df.groupby('model')['phonetische_aehnlichkeit'].mean()
            leaderboard_df['Average Phonetische Ähnlichkeit Score'] = phon_avg_series

        leaderboard_df = leaderboard_df.sort_values(by='avg_gesamt_score', ascending=False)
        leaderboard_df = leaderboard_df.reset_index()

        rename_map = {
            'model': 'Model Name',
            'num_runs': 'Number of Runs',
            'avg_gesamt_score': 'Average Gesamt Score'
        }
        leaderboard_df = leaderboard_df.rename(columns=rename_map)

        final_columns = ['Model Name', 'Number of Runs', 'Average Gesamt Score']
        if 'Average Phonetische Ähnlichkeit Score' in leaderboard_df.columns:
            final_columns.append('Average Phonetische Ähnlichkeit Score')

        leaderboard_df = leaderboard_df[[col for col in final_columns if col in leaderboard_df.columns]]

        return leaderboard_df

    except Exception:
        return pd.DataFrame()


def main_dashboard():
    """
    Main function to render the Streamlit dashboard.
    """
    st.set_page_config(page_title="Schwerhörige-Hexe Benchmark Dashboard", layout="wide")
    st.title("Schwerhörige-Hexe Benchmark Dashboard")

    # --- Sidebar for Run Selection ---
    st.sidebar.header("Run Selection")

    # Allow user to specify base benchmark directory - useful if multiple benchmark sets exist
    # For simplicity now, hardcoding, but could be an st.text_input in sidebar
    base_dir_for_runs = "benchmarks_output"

    available_runs = get_available_run_ids(base_dir_for_runs)

    if not available_runs:
        st.sidebar.warning(f"No benchmark runs found in '{Path(base_dir_for_runs).resolve()}/'. "
                           "Ensure benchmark runs have completed and produced output including the SQLite DB.")
        st.info("How to get started:", icon="🚀")
        st.markdown(
            """
            1. Run a benchmark using the CLI: `hexe-bench run --model <your-model> -n <num-runs>`
            2. Ensure the output directory (default: `benchmarks_output/`) contains subdirectories for each run.
            3. Each run directory should have a `..._benchmark_data.sqlite` file.
            """
        )
        st.stop() # Stop execution if no runs are available to select

    selected_run_id = st.sidebar.selectbox("Select a Benchmark Run:", available_runs)

    if not selected_run_id: # Should not happen if available_runs is not empty, but as a safeguard
        st.error("No run selected.")
        st.stop()

    # --- Main Content Area ---
    st.header(f"Results for Run: {selected_run_id}")

    # Define paths based on selection
    run_path = Path(base_dir_for_runs) / selected_run_id
    db_path_str = str(run_path / f"{selected_run_id}_benchmark_data.sqlite")
    cost_csv_path_str = str(run_path / "cost_report.csv")

    # DataFrames to hold loaded data, initialize as empty
    records_df = pd.DataFrame()
    cost_df = pd.DataFrame()

    # --- Display Basic Stats (from DB) ---
    st.subheader("📊 Run Overview & Data Table")
    conn: Optional[sqlite3.Connection] = visualize._get_db_connection(db_path_str) # Use existing helper

    if conn:
        try:
            records_df = visualize._fetch_data_from_db(conn, selected_run_id) # Fetch specific run_id
            if not records_df.empty:

                col1, col2, col3 = st.columns(3)
                num_records = len(records_df)
                avg_score_gesamt = records_df['gesamt'].mean() if 'gesamt' in records_df.columns else 'N/A'
                total_cost_from_db = records_df['cost_usd'].sum() if 'cost_usd' in records_df.columns else 'N/A'

                col1.metric("Total Records Processed", num_records)
                col2.metric("Avg. 'Gesamt' Score", f"{avg_score_gesamt:.2f}" if isinstance(avg_score_gesamt, float) else avg_score_gesamt)
                col3.metric("Total Cost (from DB records)", f"${total_cost_from_db:.4f}" if isinstance(total_cost_from_db, float) else total_cost_from_db)

                with st.expander("View Raw Data Table (first 100 rows)", expanded=False):
                    st.dataframe(records_df.head(100), use_container_width=True)
            else:
                st.warning("No records found in the database for this run.")

        # --- Leaderboard Section ---
        st.subheader("🏆 Model Performance Leaderboard for this Run")
        leaderboard_df = create_leaderboard_df(records_df)
        if not leaderboard_df.empty:
            st.dataframe(leaderboard_df, use_container_width=True)
        else:
            st.info("No data available to build leaderboard for this run. This could be due to missing data or an issue in processing.")

        except Exception as e:
            st.error(f"Error loading data from database: {e}")
            logger.error(f"DB Error for {selected_run_id}: {e}", exc_info=True)
        finally:
            conn.close()
    else:
        st.error(f"Could not connect to database: {db_path_str}")

    # --- Display Plots (from visualize.py) ---
    st.subheader("📈 Visualizations")

    if not records_df.empty:
        # Scores Boxplots
        st.markdown("#### Score Distributions by Model")
        col_score_1, col_score_2 = st.columns(2)
        with col_score_1:
            fig_gesamt_scores = visualize.create_scores_boxplot(records_df, score_column='gesamt', title_prefix="")
            if fig_gesamt_scores:
                st.plotly_chart(fig_gesamt_scores, use_container_width=True)
            else:
                st.caption("Could not generate 'Gesamt' scores boxplot.")

        with col_score_2:
            fig_phon_scores = visualize.create_scores_boxplot(records_df, score_column='phonetische_aehnlichkeit', title_prefix="")
            if fig_phon_scores:
                st.plotly_chart(fig_phon_scores, use_container_width=True)
            else:
                st.caption("Could not generate 'Phonetische Ähnlichkeit' scores boxplot.")
        # Add more score plots as desired (e.g., in more columns or an expander)

    else: # records_df is empty
        st.info("Score visualizations cannot be generated as no record data was loaded from the database.")

    # Cost Plot
    st.markdown("#### Cost Analysis")
    cost_csv_file = Path(cost_csv_path_str)
    if cost_csv_file.exists() and cost_csv_file.is_file():
        try:
            cost_df = pd.read_csv(cost_csv_file)
            if not cost_df.empty:
                fig_cost = visualize.create_cost_plot(cost_df, title_prefix="")
                if fig_cost:
                    st.plotly_chart(fig_cost, use_container_width=True)
                else:
                    st.caption("Could not generate cost plot from CSV data.")
            else:
                st.caption(f"Cost report ({cost_csv_file.name}) is empty.")
        except pd.errors.EmptyDataError:
             st.caption(f"Cost report ({cost_csv_file.name}) is empty (pandas EmptyDataError).")
        except Exception as e:
            st.error(f"Error loading cost data from {cost_csv_file.name}: {e}")
            logger.error(f"Cost CSV Error for {selected_run_id}: {e}", exc_info=True)
    else:
        st.caption(f"Cost report not found at: {cost_csv_path_str}")

    # Placeholder for more advanced analytics/comparisons
    st.sidebar.markdown("---")
    st.sidebar.info("Future features: Compare runs, detailed model views, custom plot parameters.")

# To run this dashboard:
# 1. Ensure you have benchmark data in `benchmarks_output/` (or as specified).
# 2. In your terminal, navigate to the root of the project.
# 3. Run: `poetry run streamlit run src/analytics/dashboard.py`
# (Or if your environment is already activated: `streamlit run src/analytics/dashboard.py`)
if __name__ == "__main__":
    # This allows running `python src/analytics/dashboard.py` for local development,
    # but `streamlit run src/analytics/dashboard.py` is the standard way.
    # Note: Streamlit's execution model means this `if __name__ == "__main__":` block
    # will run, and then Streamlit takes over the script from the top.
    # It's common to put the main app logic in a function and call it, as done here.
    main_dashboard()


