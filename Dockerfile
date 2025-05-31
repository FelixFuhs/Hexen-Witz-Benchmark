# Use an official Python runtime as a parent image
FROM python:3.11-slim

# Set environment variables
# PYTHONUNBUFFERED: Prevents Python from buffering stdout and stderr
# PIP_NO_CACHE_DIR: Disables pip's cache, reducing image size
# PIP_DISABLE_PIP_VERSION_CHECK: Suppresses warnings about pip version
# POETRY_VERSION: Specifies the version of Poetry to install
# POETRY_VIRTUALENVS_CREATE=false: Tells Poetry to install packages in the system's site-packages (within the image)
# POETRY_HOME: Specifies the installation directory for Poetry
ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=off \
    PIP_DISABLE_PIP_VERSION_CHECK=on \
    POETRY_VERSION=1.8.2 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_HOME="/opt/poetry"
# Add Poetry's bin directory to the PATH
ENV PATH="$POETRY_HOME/bin:$PATH"

# Install system dependencies for Poetry (curl) and potentially for building Python packages.
# Clean up apt cache and remove curl afterwards to keep the image slim.
RUN apt-get update && apt-get install -y --no-install-recommends curl \
    # Add other build-time system dependencies here if any Python package needs them for compilation
    # For example: build-essential, libssl-dev, libffi-dev, etc.
    && curl -sSL https://install.python-poetry.org | python - \
    && apt-get remove -y curl \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory in the image
WORKDIR /app

# Copy only the files necessary for dependency installation first.
# This leverages Docker's layer caching. If these files don't change,
# the following RUN poetry install layer won't be re-executed.
COPY pyproject.toml poetry.lock* ./

# Install project dependencies (including the project itself and its scripts, if defined in pyproject.toml).
# --no-dev: Excludes development dependencies like pytest, ruff, mypy.
# --no-interaction: Prevents Poetry from asking interactive questions.
# --no-ansi: Disables ANSI color output.
# This command installs dependencies specified in poetry.lock (if present and consistent) or pyproject.toml.
# Since POETRY_VIRTUALENVS_CREATE=false, packages are installed into the global site-packages.
RUN poetry install --no-dev --no-interaction --no-ansi

# Copy the rest of the application code into the image.
# This includes your `src` directory and any other files needed by the application.
COPY . .

# Create a non-root user and group for security best practices.
# Running applications as a non-root user limits potential damage if the application is compromised.
RUN groupadd -r appgroup && useradd --no-log-init -r -g appgroup appuser

# Change ownership of the /app directory and its contents to the new non-root user.
# This is important because previous operations (like COPY) might have been done as root.
RUN chown -R appuser:appgroup /app

# Switch to the non-root user. Subsequent commands will be run as this user.
USER appuser

# Set the entrypoint for the Docker image.
# This is the command that will be executed when the container starts if no other command is specified.
# 'hexe-bench' should be available on the PATH because Poetry installs scripts from pyproject.toml.
ENTRYPOINT ["hexe-bench"]

# Default command to append to the entrypoint if no command is provided to `docker run`.
# For 'hexe-bench', '--help' is a sensible default to show usage instructions.
CMD ["--help"]
