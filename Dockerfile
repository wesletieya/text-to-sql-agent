FROM python:3.11-slim

WORKDIR /app
RUN pip install --no-cache-dir uv==0.13.0

# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev --no-install-project

COPY agent ./agent
COPY app ./app
COPY eval/__init__.py eval/pricing.yaml ./eval/
COPY semantic ./semantic

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

EXPOSE 8000 8501
