FROM ghcr.io/ggml-org/whisper.cpp:main-vulkan

RUN apt-get update && \
    apt-get install -y --no-install-recommends wget curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY entrypoint.sh /app/entrypoint.sh
COPY download-model.sh /app/download-model.sh
RUN chmod +x /app/entrypoint.sh /app/download-model.sh

ENV MODEL_DIR=/models
ENV WHISPER_MODEL=base.en
ENV STT_PORT=8080

EXPOSE 8080

ENTRYPOINT ["/app/entrypoint.sh"]
