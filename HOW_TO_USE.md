# How to Use the Schwerhörige-Hexe Benchmark

This guide provides detailed instructions on how to set up, configure, and run the Schwerhörige-Hexe Benchmark, and how to understand its outputs.

## Table of Contents

- [Prerequisites](#prerequisites)
- [Setup & Installation](#setup--installation)
- [Configuration](#configuration)
- [Running the Benchmark](#running-the-benchmark)
- [Output Structure](#output-structure)
- [Interpreting Results](#interpreting-results)
- [Troubleshooting](#troubleshooting)

## Prerequisites

Before you begin, ensure you have the following installed:

- **Python**: Version 3.11 or higher.
- **Poetry**: Version 1.8.0 or higher (for dependency management). You can find installation instructions at [python-poetry.org](https://python-poetry.org/docs/#installation).
- **Git**: For cloning the repository.

## Setup & Installation

1.  **Clone the Repository**:
    ```bash
    git clone https://github.com/tschuegge/schwerhoerige-hexe-benchmark.git # Replace with your repo URL if different
    cd schwerhoerige-hexe-benchmark
    ```

2.  **Install Dependencies**:
    Poetry will handle the installation of all necessary dependencies.
    ```bash
    poetry install
    ```
    This command creates a virtual environment (usually in `.venv/` within the project directory) and installs all packages listed in `pyproject.toml`.

## Configuration

The benchmark requires API keys and can be configured via environment variables or a `.env` file.

1.  **Create `.env` File**:
    Copy the example environment file to create your own local configuration:
    ```bash
    cp .env.example .env
    ```

2.  **Set Environment Variables**:
    Edit the `.env` file and provide the necessary values. Key variables include:

    -   `OPENROUTER_API_KEY` (Required): Your API key for OpenRouter.ai. This is essential for making calls to the LLMs.
    -   `MAX_BUDGET_USD` (Optional, Default: `100.0` in `src/config.py`): The maximum USD budget for a benchmark run. The run will attempt to stop gracefully if this budget is exceeded.
    -   `JUDGE_MODEL_NAME` (Optional, Default: `"openai/gpt-4o"` in `src/config.py`): The model used for judging the generated jokes. It's recommended to use a powerful model for best results.
    -   `LOG_LEVEL` (Optional, Default: `INFO` if not set by CLI): Sets the application's base logging level (e.g., `DEBUG`, `INFO`, `WARNING`, `ERROR`). The CLI's `--log-level` option can override this for a specific run.

    You can also set these variables directly in your shell environment, but a `.env` file is recommended for ease of use. The application uses `pydantic-settings` which will prioritize environment variables over values in a `.env` file if both are set.

## Running the Benchmark

The benchmark is run using the `hexe-bench` command-line interface (CLI). You can activate the Poetry-managed environment first if `hexe-bench` isn't globally available on your PATH:

```bash
poetry shell  # Activates the virtual environment
hexe-bench --help # Shows all available commands and options
```
Alternatively, you can run CLI commands directly using `poetry run hexe-bench ...`.

### `run` Command

The primary command to execute a benchmark run is `run`.

**Syntax**:
```bash
hexe-bench run [OPTIONS]
```

**Key Options**:

-   `-m, --model TEXT`: Specify one or more LLM models to benchmark (e.g., `mistralai/mistral-7b-instruct`). This option can be used multiple times:
    `hexe-bench run -m model1 -m model2`
-   `-n, --num-runs INTEGER`: Number of jokes to generate per model (Default: `1`).
-   `-id, --run-id TEXT`: Assign a custom ID to this benchmark run. If not provided, a timestamp-based ID will be generated (e.g., `run_YYYYMMDD_HHMMSS`).
-   `-c, --config TEXT`: Path to a custom `.env` configuration file (e.g., `path/to/my.env`).
-   `-o, --output-dir TEXT`: Base directory where benchmark outputs will be saved (Default: `benchmarks_output/`).
-   `-ll, --log-level TEXT`: Set the logging level for the run (DEBUG, INFO, WARNING, ERROR, CRITICAL. Default: `INFO`).

**Example Commands**:

-   Run with a specific model for 3 generations:
    ```bash
    hexe-bench run --model "mistralai/mistral-small-latest" --num-runs 3
    ```
-   Run with multiple models and a custom run ID:
    ```bash
    hexe-bench run -m "openai/gpt-3.5-turbo" -m "anthropic/claude-3-haiku-20240307" --num-runs 5 --run-id "my_comparison_run_01"
    ```
-   Run using a specific configuration file and output directory:
    ```bash
    hexe-bench run --config ".env.custom" --output-dir "results/experiment_A"
    ```

### Other Commands (Placeholders)

-   `hexe-bench resume RUN_ID`: (Not yet implemented) Intended to resume an interrupted run.
-   `hexe-bench stats RUN_ID`: (Not yet implemented) Intended to display statistics for a run.

## Output Structure

All outputs for a benchmark run are stored in a directory named after the `run_id` within the specified output directory (default: `benchmarks_output/<run_id>/`).

-   `benchmarks_output/<run_id>/`:
    -   `raw/`: Contains JSON files for each raw generation result from the LLMs, named `<model_name_sanitized>_<run_number>.json`. Each file is a `GenerationResult` object.
    -   `judged/`: Contains JSON files for each judged benchmark record, named `<model_name_sanitized>_<run_number>.json`. Each file is a `BenchmarkRecord` object (combining generation and judge scores).
    -   `plots/`: Contains visualizations generated for the run (e.g., `scores_gesamt_boxplot.html/.png`, `cost_per_model_barchart.html/.png`).
    -   `<run_id>_benchmark_data.sqlite`: An SQLite database file containing all benchmark records in a structured format for easier querying and analysis.
    -   `cost_report.csv`: A CSV file logging the cost, prompt tokens, and completion tokens for each generation call.
    -   `meta.json`: Contains metadata about the benchmark run, including the (non-sensitive) configuration settings used and timestamps.

## Interpreting Results

1.  **Visualizations**:
    Open the HTML files in the `plots/` directory in a web browser to view interactive charts (e.g., score distributions per model, cost breakdowns). PNG files provide static versions for embedding in reports.

2.  **SQLite Database**:
    You can use any SQLite database browser (e.g., DB Browser for SQLite, DBeaver, VS Code extensions) to open the `<run_id>_benchmark_data.sqlite` file. The main table is `records`, where you can query and analyze the detailed results.

3.  **Streamlit Dashboard**:
    To view an interactive dashboard summarizing the results:
    ```bash
    poetry run streamlit run src/analytics/dashboard.py
    ```
    Then, open the URL provided by Streamlit (usually `http://localhost:8501`) in your web browser. You can select the desired `run_id` from the dashboard's sidebar to load and view its data.

4.  **Raw Data**:
    The JSON files in `raw/` and `judged/`, along with `cost_report.csv`, provide the most granular data if you need to perform custom analysis (e.g., with Python scripts using Pandas, or in a Jupyter Notebook).

## Troubleshooting

-   **API Key Issues**: Ensure `OPENROUTER_API_KEY` is correctly set in your `.env` file or environment and that it has sufficient credits/access for the models you are trying to use. Check for typos.
-   **Dependency Problems**: If you encounter issues after pulling new changes or switching branches, try re-installing dependencies:
    ```bash
    poetry install
    ```
    You can also try updating dependencies if issues persist: `poetry update`.
-   **Model Not Found/Access Denied**: OpenRouter might not grant access to all models for all API keys, or model names might change. Check the OpenRouter documentation for model availability and correct identifiers.
-   **Plotly Image Export Issues**: If PNG image saving fails (often with messages related to `kaleido`), ensure `kaleido` is correctly installed. `poetry install` should handle this. On some systems, additional dependencies for Kaleido might be needed (though less common with its pre-built binaries). Check the Plotly and Kaleido documentation.
-   **Log Files**: Check the console output for log messages. Increase log verbosity with `hexe-bench run --log-level DEBUG` for more detailed information if you encounter issues. The logs are printed to standard error/output.
-   **File Not Found (Prompts)**: The benchmark expects prompt files (`benchmark_prompt.md`, `judge_checklist.md`) in the `src/prompts/` directory. If these are missing, `main.py` or `judge.py` will attempt to create basic dummy versions, but for actual benchmark runs, ensure your custom prompts are correctly placed.

---

*This document will be updated as new features are added or existing ones change.*
