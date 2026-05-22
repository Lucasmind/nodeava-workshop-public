# Kokoro-FastAPI built for AMD ROCm GPUs
# First build takes ~20-30 min, then cached. Image is ~22GB (ROCm base is large).
# MIOpen auto-tunes kernel shapes on first synthesis (~30-60s warmup).

FROM rocm/dev-ubuntu-24.04:6.4.4-complete

ENV DEBIAN_FRONTEND=noninteractive

# Install Python and dependencies
RUN apt-get update && apt-get install -y \
    python3.10 \
    python3-venv \
    espeak-ng \
    espeak-ng-data \
    git \
    libsndfile1 \
    curl \
    ffmpeg \
    g++ \
 && apt-get clean && rm -rf /var/lib/apt/lists/* \
 && mkdir -p /usr/share/espeak-ng-data \
 && ln -s /usr/lib/*/espeak-ng-data/* /usr/share/espeak-ng-data/

# Install UV package manager
RUN curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mv /root/.local/bin/uv /usr/local/bin/ && \
    mv /root/.local/bin/uvx /usr/local/bin/

# Create non-root user
RUN useradd -m -u 1001 appuser && \
    mkdir -p /app/api/src/models/v1_0 && \
    chown -R appuser:appuser /app

USER appuser
WORKDIR /app

# Clone Kokoro-FastAPI at v0.2.4
RUN git clone --branch v0.2.4 --depth 1 https://github.com/remsky/Kokoro-FastAPI.git /tmp/kokoro && \
    cp /tmp/kokoro/pyproject.toml /app/pyproject.toml && \
    cp -r /tmp/kokoro/api /app/api && \
    cp -r /tmp/kokoro/web /app/web && \
    cp /tmp/kokoro/docker/scripts/* /app/ && \
    chmod +x /app/entrypoint.sh && \
    rm -rf /tmp/kokoro

ENV PHONEMIZER_ESPEAK_PATH=/usr/bin \
    PHONEMIZER_ESPEAK_DATA=/usr/share/espeak-ng-data \
    ESPEAK_DATA_PATH=/usr/share/espeak-ng-data

# Install dependencies — use ROCm PyTorch instead of CUDA
RUN uv venv --python 3.10 && \
    . /app/.venv/bin/activate && \
    uv pip install torch==2.8.0 --index-url https://download.pytorch.org/whl/rocm6.4 && \
    uv sync --extra gpu --no-install-project

ENV PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app:/app/api \
    PATH="/app/.venv/bin:$PATH" \
    UV_LINK_MODE=copy \
    USE_GPU=true \
    DEVICE=gpu \
    HSA_OVERRIDE_GFX_VERSION=11.0.0

# Download model at build time
RUN python download_model.py --output api/src/models/v1_0

CMD ["./entrypoint.sh"]
