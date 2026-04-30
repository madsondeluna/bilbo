FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/

RUN pip install --no-cache-dir -e .

COPY data/ ./data/

VOLUME ["/app/builds", "/app/data"]

ENV BILBO_DB_PATH=/app/builds/.bilbo/bilbo.db

ENTRYPOINT ["bilbo"]
CMD ["--help"]
