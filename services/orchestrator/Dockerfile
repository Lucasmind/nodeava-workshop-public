FROM python:3.12-slim

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Build context is ./services (per docker-compose). Layout inside:
#   orchestrator/  → the orchestrator app
#   wiki-compiler/ → the wiki compiler invoked by /v1/ingest
COPY orchestrator/requirements.txt orchestrator/pyproject.toml ./
COPY orchestrator/orchestrator/ ./orchestrator/

# Copy the wiki-compiler so the ingest pipeline can invoke it.
# Plan #6: the compiler is a separate Python project; it lives at
# /app/wiki-compiler inside the container and shares the orchestrator's
# venv. The orchestrator's ingest runner shells out to compile_wiki.py.
COPY wiki-compiler/ /app/wiki-compiler/

# Combined install: orchestrator deps + compiler deps + editable install.
RUN pip install --no-cache-dir -r requirements.txt \
    && pip install --no-cache-dir -r /app/wiki-compiler/requirements.txt \
    && pip install --no-cache-dir -e .

EXPOSE 8082

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8082/health || exit 1

CMD ["python", "-m", "orchestrator.main"]
