FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src/ ./src/
COPY web/ ./web/

RUN pip install --no-cache-dir -e ".[web]"

COPY data/ ./data/

ENV BILBO_DB_PATH=/tmp/bilbo.db
ENV PORT=8000

EXPOSE 8000

CMD ["sh", "-c", "uvicorn web.app:app --host 0.0.0.0 --port ${PORT}"]
