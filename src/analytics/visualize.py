import logging
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Optional

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px

logger = logging.getLogger(__name__)

def _get_db_connection(db_path_str: str) -> Optional[sqlite3.Connection]:
    """
    Establishes a read-only connection to the SQLite database.
    """
    db_path = Path(db_path_str)
    if not db_path.exists():
        logger.error(f"Database file not found at {db_path_str}")
        return None
    try:
        # URI mode allows specifying flags like mode=ro
        conn = sqlite3.connect(f"file:{db_path_str}?mode=ro", uri=True)
        logger.info(f"Read-only SQLite connection established to {db_path_str}")
        return conn
    except sqlite3.Error as e:
        logger.error(f"Error connecting to SQLite database {db_path_str} in read-only mode: {e}", exc_info=True)
        return None

def _fetch_data_from_db(conn: sqlite3.Connection, run_id: Optional[str] = None) -> pd.DataFrame:
    """
    Fetches data from the 'records' table into a Pandas DataFrame.
    Filters by run_id if provided.
    """
    query = "SELECT * FROM records"
    params: Optional[tuple] = None
    if run_id:
        query += " WHERE run_id = ?"
        params = (run_id,)

    try:
        df = pd.read_sql_query(query, conn, params=params)
        logger.info(f"Fetched {len(df)} records from DB" + (f" for run_id {run_id}" if run_id else ""))
        return df
    except pd.io.sql.DatabaseError as e: # Specific pandas error for DB issues
        logger.error(f"Error fetching data from 'records' table: {e}. "
                     "This might happen if the table doesn't exist or the DB is corrupted.", exc_info=True)
        return pd.DataFrame() # Return empty DataFrame on error
    except Exception as e:
        logger.error(f"An unexpected error occurred while fetching data from DB: {e}", exc_info=True)
        return pd.DataFrame()


def create_scores_boxplot(df: pd.DataFrame, score_column: str = 'gesamt', title_prefix: str = '') -> Optional[go.Figure]:
    """
    Creates a boxplot of scores by model from the given DataFrame.
    """
    if df.empty:
        logger.warning(f"DataFrame is empty, cannot generate boxplot for score '{score_column}'.")
        return None
    if score_column not in df.columns:
        logger.warning(f"Score column '{score_column}' not found in DataFrame. Available: {df.columns.tolist()}")
        return None
    if 'model' not in df.columns:
        logger.warning(f"Model column 'model' not found in DataFrame. Available: {df.columns.tolist()}")
        return None

    try:
        fig = px.box(
            df,
            x='model',
            y=score_column,
            color='model',
            title=f"{title_prefix}Scores Distribution by Model ({score_column})",
            points='all', # Show all data points
            labels={'model': 'Model', score_column: score_column.replace('_', ' ').title()}
        )
        fig.update_layout(
            xaxis_title="Model",
            yaxis_title=score_column.replace('_', ' ').title(),
            showlegend=False # Color is mapped to x, legend is redundant
        )
        logger.info(f"Created boxplot for score '{score_column}'.")
        return fig
    except Exception as e:
        logger.error(f"Error creating boxplot for score '{score_column}': {e}", exc_info=True)
        return None


def create_cost_plot(cost_report_df: pd.DataFrame, title_prefix: str = '') -> Optional[go.Figure]:
    """
    Creates a bar chart of total cost per model from the cost report DataFrame.
    """
    if cost_report_df.empty:
        logger.warning("Cost report DataFrame is empty, cannot generate cost plot.")
        return None
    if 'model' not in cost_report_df.columns or 'cost_usd' not in cost_report_df.columns:
        logger.warning("Required columns ('model', 'cost_usd') not found in cost report DataFrame.")
        return None

    try:
        # Ensure cost_usd is numeric
        cost_report_df['cost_usd'] = pd.to_numeric(cost_report_df['cost_usd'], errors='coerce')
        cost_report_df.dropna(subset=['cost_usd'], inplace=True) # Drop rows where cost_usd couldn't be parsed

        cost_per_model = cost_report_df.groupby('model')['cost_usd'].sum().reset_index()

        fig = px.bar(
            cost_per_model,
            x='model',
            y='cost_usd',
            color='model',
            title=f"{title_prefix}Total Cost by Model",
            labels={'model': 'Model', 'cost_usd': 'Total Cost (USD)'}
        )
        fig.update_layout(
            xaxis_title="Model",
            yaxis_title="Total Cost (USD)",
            showlegend=False
        )
        logger.info("Created total cost by model bar chart.")
        return fig
    except Exception as e:
        logger.error(f"Error creating cost plot: {e}", exc_info=True)
        return None


def save_figure(fig: go.Figure, run_id: str, filename_base: str, base_output_dir_str: str) -> None:
    """
    Saves a Plotly figure as HTML and PNG.
    """
    plots_output_path = Path(base_output_dir_str) / run_id / "plots"
    try:
        plots_output_path.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error(f"Failed to create plot directory {plots_output_path}: {e}. Plots will not be saved.", exc_info=True)
        return

    html_path = plots_output_path / f"{filename_base}.html"
    png_path = plots_output_path / f"{filename_base}.png"

    try:
        fig.write_html(str(html_path))
        logger.info(f"Saved plot to {html_path}")
        try:
            fig.write_image(str(png_path), scale=2) 
            logger.info(f"Saved plot to {png_path}")
        except Exception as e_img: 
            logger.error(f"Error saving plot to static image {png_path}: {e_img}. "
                         "Ensure Kaleido is installed and working correctly. HTML version might still be available.", exc_info=True)
    except Exception as e_html:
        logger.error(f"Error saving plot to HTML {html_path}: {e_html}", exc_info=True)


def generate_standard_visualizations(run_id: str, base_benchmark_dir: str) -> None:
    """
    Main orchestrating function to generate and save standard visualizations for a run.
    """
    logger.info(f"Starting visualization generation for run_id: {run_id}")
    run_path = Path(base_benchmark_dir) / run_id
    db_path_str = str(run_path / f"{run_id}_benchmark_data.sqlite")
    cost_csv_path_str = str(run_path / "cost_report.csv")

    conn = _get_db_connection(db_path_str)
    if not conn:
        logger.error(f"Cannot generate visualizations as DB connection to {db_path_str} failed.")
        return

    try:
        records_df = _fetch_data_from_db(conn, run_id)
        if not records_df.empty:
            fig_boxplot_gesamt = create_scores_boxplot(
                records_df, score_column='gesamt', title_prefix=f"Run {run_id}: "
            )
            if fig_boxplot_gesamt:
                save_figure(fig_boxplot_gesamt, run_id, "scores_gesamt_boxplot", base_benchmark_dir)

            fig_boxplot_phon = create_scores_boxplot(
                records_df, score_column='phonetische_aehnlichkeit', title_prefix=f"Run {run_id}: "
            )
            if fig_boxplot_phon:
                save_figure(fig_boxplot_phon, run_id, "scores_phonetische_aehnlichkeit_boxplot", base_benchmark_dir)
        else:
            logger.warning(f"No records found in DB for run_id {run_id} to generate score plots.")
    except Exception as e:
        logger.error(f"Error during score plot generation from DB for run {run_id}: {e}", exc_info=True)
    finally:
        logger.debug(f"Closing DB connection for run {run_id} visualizations.")
        conn.close()

    cost_csv_file = Path(cost_csv_path_str)
    if cost_csv_file.exists():
        try:
            cost_df = pd.read_csv(cost_csv_file)
            if not cost_df.empty:
                fig_cost_per_model = create_cost_plot(cost_df, title_prefix=f"Run {run_id}: ")
                if fig_cost_per_model:
                    save_figure(fig_cost_per_model, run_id, "cost_per_model_barchart", base_benchmark_dir)
            else:
                logger.warning(f"Cost report {cost_csv_path_str} is empty.")
        except pd.errors.EmptyDataError:
             logger.warning(f"Cost report {cost_csv_path_str} is empty (pandas EmptyDataError).")
        except Exception as e:
            logger.error(f"Failed to process cost report {cost_csv_path_str}: {e}", exc_info=True)
    else:
        logger.warning(f"Cost report {cost_csv_path_str} not found.")

    logger.info(f"Visualization generation finished for run_id: {run_id}")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    test_run_id_to_visualize = "test_run_CHANGE_ME" 
    test_base_output_dir = "benchmarks_output" 

    if "CHANGE_ME" in test_run_id_to_visualize:
        logger.warning("Please update 'test_run_id_to_visualize' in visualize.py's __main__ block "
                       "to an actual run_id from your benchmark outputs to test visualizations.")
        try:
            p = Path(test_base_output_dir)
            if p.exists():
                potential_runs = sorted([d.name for d in p.iterdir() if d.is_dir() and d.name.startswith("run_")])
                if potential_runs:
                    test_run_id_to_visualize = potential_runs[-1]
                    logger.info(f"Auto-selected most recent run_id for visualization test: {test_run_id_to_visualize}")
                else:
                    logger.warning(f"No run directories found in {test_base_output_dir} to auto-select for test.")
            else:
                logger.warning(f"Base output directory {test_base_output_dir} not found. Cannot auto-select run_id.")

        except Exception as e_auto:
            logger.error(f"Error during auto-selection of run_id: {e_auto}")

    if "CHANGE_ME" not in test_run_id_to_visualize and Path(test_base_output_dir, test_run_id_to_visualize).exists():
        logger.info(f"Attempting to generate visualizations for run_id='{test_run_id_to_visualize}' "
                    f"in base_directory='{test_base_output_dir}'")
        generate_standard_visualizations(
            run_id=test_run_id_to_visualize,
            base_benchmark_dir=test_base_output_dir
        )
    else:
        logger.error(f"Test run directory '{Path(test_base_output_dir, test_run_id_to_visualize)}' not found or "
                       "test_run_id_to_visualize is still a placeholder. Skipping __main__ test for visualize.py.")