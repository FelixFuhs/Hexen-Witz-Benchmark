import asyncio
import logging
import typer
from typing import List, Optional
from pathlib import Path

# Assuming src.main and its dependencies are structured to be importable
from src.main import run_benchmark
from rich.logging import RichHandler
from rich.console import Console

# Setup Typer App
app = typer.Typer(
    help="Schwerhörige-Hexe Benchmark CLI - A tool to benchmark LLM phonetic pun understanding.",
    name="hexe-bench",
    no_args_is_help=True,
    add_completion=False # Disable shell completion for simplicity for now
)

# Setup Rich Console and Logging
console = Console()
# Configure logging for CLI. This will be the effective logging config when CLI is used.
# It's important this is configured before any loggers are created and used if we want RichHandler from the start.
# However, modules might initialize their own loggers upon import.
# For robust RichHandler integration, it's often best to configure this as early as possible.
LOG_FORMAT = "%(message)s" # RichHandler handles timestamp and level display
logging.basicConfig(
    level="INFO", # Default level, can be overridden by CLI option
    format=LOG_FORMAT,
    datefmt="[%X]", # Used by standard handlers, RichHandler has its own
    handlers=[RichHandler(rich_tracebacks=True, console=console, markup=True, show_path=False)] # show_path=False to simplify log lines
)
# Get a logger instance for this module, or use a project-wide one
# Using a specific name allows for potential future specific configuration.
logger = logging.getLogger("schwerhoerige_hexe_benchmark.cli")


@app.command()
def run(
    models: Optional[List[str]] = typer.Option(
        None, "--model", "-m",
        help="Model(s) to run (e.g., 'openai/gpt-3.5-turbo'). Can be specified multiple times. If None, uses default from main.",
        show_default=False # Default is None, which means main.py handles its internal default
    ),
    num_runs: int = typer.Option(
        1, "--num-runs", "-n",
        min=1,
        help="Number of generation runs per model."
    ),
    run_id: Optional[str] = typer.Option(
        None, "--run-id", "-id",
        help="Custom run ID for the benchmark. Timestamped if None.",
        show_default=False
    ),
    config_file: Optional[str] = typer.Option(
        None, "--config", "-c",
        help="Path to custom .env configuration file (e.g., 'path/to/my.env').",
        exists=True, dir_okay=False, resolve_path=True # Ensure it's a file if provided
    ),
    output_dir: str = typer.Option(
        "benchmarks_output", "--output-dir", "-o",
        help="Base directory for benchmark outputs.",
        writable=True, resolve_path=True # Ensure output_dir is writable
    ),
    log_level: str = typer.Option(
        "INFO", "--log-level", "-ll",
        help="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL).",
        case_sensitive=False
    )
) -> None:
    """
    Runs the Schwerhörige-Hexe benchmark with the specified models and parameters.
    """
    numeric_log_level = getattr(logging, log_level.upper(), None)
    if not isinstance(numeric_log_level, int):
        logger.error(f"Invalid log level: {log_level}. Using INFO.")
        numeric_log_level = logging.INFO

    # Set the level for all loggers used by the project if they share a common root or are configured to inherit.
    # This sets the root logger's level. Child loggers will inherit unless they have their own level set.
    logging.getLogger().setLevel(numeric_log_level)
    logger.info(f"Log level set to: {log_level.upper()}") # This logger instance will use the new level.

    logger.info("Starting benchmark run command via CLI...")

    # Typer converts Option(None) for List[str] to an empty list [] if the option is provided multiple times but then cleared,
    # or if default is an empty list. If --model is not used, 'models' is None.
    # If --model is used like "--model foo --model bar" it's a list.
    # If --model is used with no argument (if Typer allowed that), or if its default_factory=list, it could be [].
    # The current setup: models is None if not provided, or List[str] if provided.
    models_to_pass = models if models else None # run_benchmark handles None by using its own default

    # Create the output directory path object. Typer's writable=True ensures it can be created.
    # The actual directory creation is handled by run_benchmark or storage.files.ensure_dir_structure.
    output_dir_path = Path(output_dir)

    asyncio.run(run_benchmark(
        run_id=run_id,
        models_to_run=models_to_pass,
        num_runs_per_model=num_runs,
        config_file=config_file, # Pass the string path directly
        base_output_dir_str=str(output_dir_path) # Pass as string, main.py will convert to Path
    ))
    logger.info("Benchmark run command finished.")


@app.command()
def resume(
    run_id_to_resume: str = typer.Argument(
        ..., # Ellipsis indicates a required argument
        help="The ID of the previously interrupted benchmark run to resume.",
        metavar="RUN_ID" # Provides a clean name in help text
    )
) -> None:
    """
    Resumes a previously interrupted benchmark run (Not Implemented).
    """
    logger.info(f"Attempting to resume run: {run_id_to_resume}")
    console.print(f"[yellow]Resume functionality for run '{run_id_to_resume}' is not yet implemented.[/yellow]")
    # Future implementation ideas:
    # 1. Load meta.json from the run_id_to_resume.
    # 2. Determine which models/runs were completed (from raw/judged files or DB).
    # 3. Re-run only the missing generations.
    # 4. Re-run judging for all raw files that don't have corresponding judged files.


@app.command()
def stats(
    run_id_for_stats: str = typer.Argument(
        ...,
        help="The ID of the completed benchmark run to display statistics for.",
        metavar="RUN_ID"
    )
) -> None:
    """
    Displays basic statistics for a completed benchmark run (Not Implemented).
    """
    logger.info(f"Fetching stats for run: {run_id_for_stats}")
    console.print(f"[yellow]Statistics display for run '{run_id_for_stats}' is not yet implemented.[/yellow]")
    # Future implementation ideas:
    # 1. Load all judged JSON files or query the SQLite DB for the given run_id.
    # 2. Aggregate scores (average, median, min, max per category per model).
    # 3. Calculate costs per model and total.
    # 4. Display in a Rich Table or save to a CSV/Markdown file.
    # 5. Consider using pandas for data aggregation if combined.parquet is generated.


# This allows running `python src/cli.py --help` etc.
if __name__ == "__main__":
    app()
