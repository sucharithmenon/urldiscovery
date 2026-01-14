FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy dependency files
COPY pyproject.toml .

# Install the package
RUN pip install --no-cache-dir -e .

# Copy application code
COPY src/ ./src/

# Create non-root user for security
RUN useradd -m -u 1000 worker
USER worker

# Default command
ENTRYPOINT ["python", "-m", "src.cli"]

# Health check (can be added later)
# HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
#   CMD python -c "import sys; sys.exit(0)" || exit 1