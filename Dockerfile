FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY src/ src/
COPY static/ static/
COPY scripts/ scripts/

# Install Python dependencies
RUN pip install --no-cache-dir .

# Copy documents and build index
COPY rag-docs/ rag-docs/
RUN python scripts/ingest_docs.py

# Create non-root user
RUN useradd -m -r appuser && chown -R appuser:appuser /app
USER appuser

EXPOSE 9247

CMD ["python", "-m", "lgac_assistant"]
