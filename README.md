# Schwerhörige-Hexe Benchmark

[![CI - Lint, Type Check & Test](https://github.com/tschuegge/schwerhoerige-hexe-benchmark/actions/workflows/ci.yml/badge.svg)](https://github.com/tschuegge/schwerhoerige-hexe-benchmark/actions/workflows/ci.yml)
<!-- TODO: Verify this CI badge URL is correct after initial push and workflow setup. -->

The "Schwerhörige-Hexe Benchmark" is an asynchronous Python framework designed to measure and evaluate how well Large Language Models (LLMs) understand and generate phonetically similar wordplay, in the style of the "deaf witch" (schwerhörige Hexe) joke structure.

## Overview

This benchmark automates the process of:
1.  **Generating** wordplay jokes using candidate LLMs via OpenRouter.
2.  **Extracting** the "desired" vs. "received" components of the pun.
3.  **Judging** the quality of the generated pun based on criteria like phonetic similarity, humor/offensiveness (Anzüglichkeit), logic, and creativity, using a powerful LLM as a judge.
4.  **Storing** all raw data, metadata, costs, and judged records persistently.
5.  **Analyzing and Visualizing** the results through plots and an interactive dashboard.

The project aims to provide a standardized way to compare LLMs on this specific nuanced task.

## Key Features

-   **Extensible LLM Support**: Leverages OpenRouter to interact with a wide variety of LLMs.
-   **Automated Judging**: Uses a separate LLM to evaluate generated content against a detailed checklist.
-   **Comprehensive Data Storage**: Saves all inputs, outputs, scores, and metadata in JSON, CSV, and an SQLite database for detailed analysis.
-   **Cost Tracking**: Monitors and reports estimated costs for LLM API calls.
-   **Budget Management**: Allows setting a maximum budget to prevent runaway costs.
-   **Data Visualization**: Generates plots for scores and costs.
-   **Interactive Dashboard**: A Streamlit application to explore benchmark results.
-   **CLI Interface**: User-friendly command-line tool built with Typer for running benchmarks.
-   **Containerized**: Dockerfile provided for easy deployment and reproducible environments.
-   **CI/CD**: GitHub Actions workflow for automated linting, type-checking, and testing.

## Technical Stack

-   Python 3.11+
-   Poetry for dependency management
-   Asyncio for concurrent operations
-   HTTPX for asynchronous HTTP requests
-   Pydantic for data validation and settings management
-   Typer for the CLI
-   Plotly for visualizations
-   Streamlit for the interactive dashboard
-   SQLite for structured data storage
-   Ruff for linting and formatting
-   MyPy for static type checking
-   Pytest for testing
-   Docker for containerization
-   GitHub Actions for CI

## Quickstart

1.  **Prerequisites**:
    -   Python 3.11+
    -   Poetry (>=1.8.0 recommended, installed version: 1.8.2)
    -   Git

2.  **Clone & Install**:
    ```bash
    git clone https://github.com/tschuegge/schwerhoerige-hexe-benchmark.git
    # TODO: Verify this is the correct public repository URL after creation.
    cd schwerhoerige-hexe-benchmark
    poetry install
    ```

3.  **Configure**:
    Copy the environment variable template and fill in your API key:
    ```bash
    cp .env.example .env
    ```
    Then, edit `.env` and add your `OPENROUTER_API_KEY`. For detailed configuration options, see [HOW_TO_USE.md](./HOW_TO_USE.md).

4.  **Run a Benchmark**:
    First, activate the virtual environment managed by Poetry:
    ```bash
    poetry shell
    ```
    Then, run the benchmark CLI:
    ```bash
    hexe-bench run --model "mistralai/mistral-small-latest" --num-runs 3
    ```
    (Alternatively, without activating the shell: `poetry run hexe-bench run ...`)

5.  **View Results**:
    -   Outputs are saved in `benchmarks_output/<run_id>/` by default.
    -   Launch the interactive dashboard:
        ```bash
        streamlit run src/analytics/dashboard.py
        ```
        (Or from an activated shell: `poetry run streamlit run src/analytics/dashboard.py`)

For more detailed instructions on setup, configuration, all CLI options, output structure, and troubleshooting, please refer to the **[HOW_TO_USE.md](./HOW_TO_USE.md)** guide.

## Project Structure

-   `src/`: Main application source code.
    -   `analytics/`: Data visualization (`visualize.py`) and dashboard (`dashboard.py`) modules.
    -   `prompts/`: Contains template files for prompts (e.g., `benchmark_prompt.md`, `judge_checklist.md`).
    -   `storage/`: Data persistence modules for file-based storage (`files.py`) and database (`database.py`).
    -   `config.py`: Pydantic settings management (`Settings` class).
    -   `models.py`: Pydantic data models (e.g., `GenerationResult`, `JudgeScore`, `BenchmarkRecord`).
    -   `router_client.py`: Client for interacting with the OpenRouter API.
    -   `generator.py`: Logic for generating jokes using LLMs.
    -   `extractor.py`: Logic for extracting structured summary from LLM responses.
    -   `judge.py`: Logic for judging the quality of generated jokes using an LLM.
    -   `main.py`: Core benchmark orchestration logic called by the CLI.
    -   `cli.py`: Command-line interface built with Typer.
-   `tests/`: Unit and integration tests for the application modules.
-   `benchmarks_output/`: Default directory where benchmark run outputs are stored (this directory is git-ignored).
-   `Dockerfile`: For building the application's Docker image.
-   `.github/workflows/`: Contains GitHub Actions CI/CD workflow configurations (e.g., `ci.yml`).
-   `pyproject.toml`: Project metadata, dependencies, and tool configurations (Poetry, Ruff, MyPy, Pytest).
-   `poetry.lock`: Precise dependency versions.
-   `.env.example`: Template for environment variable configuration.
-   `HOW_TO_USE.md`: Detailed user guide for setting up and running the benchmark.
-   `TECHNICAL_SPEC.md`: Detailed technical specification of the project.
-   `LICENSE`: Project's MIT License file.

## Contributing

Contributions are welcome! Please feel free to open an issue or submit a pull request if you have suggestions for improvements or new features.
(Further details can be added to a `CONTRIBUTING.md` file if the project grows.)

## License

This project is licensed under the MIT License. See the [LICENSE](./LICENSE) file for details.