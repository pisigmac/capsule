FROM python:3.12-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY services ./services
COPY cli ./cli
RUN pip install --no-cache-dir .

RUN mkdir -p /data/capsules /data/capsules/shared /data/capsules/archived

ENV CAPSULES_DIR=/data/capsules \
    API_HOST=0.0.0.0 \
    API_PORT=9000 \
    CAPSULE_WATCH=false

EXPOSE 9000
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:9000/health || exit 1

CMD ["uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "9000", "--workers", "2"]
