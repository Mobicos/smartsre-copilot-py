FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY alembic.ini ./
COPY alembic ./alembic
COPY app ./app
COPY static ./static
COPY aiops-docs ./aiops-docs
COPY mcp_servers ./mcp_servers

RUN pip install --no-cache-dir -e .

EXPOSE 9900

CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9900"]
