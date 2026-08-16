# ==============================================================================
# InsightForge AI - production container image
# Works on Render, Railway, Fly.io, or any Docker host.
# ==============================================================================
FROM python:3.11-slim

# Prevent Python from writing .pyc files / buffering stdout (cleaner logs)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps: none required beyond build tools for a couple of wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip && pip install -r requirements.txt

COPY . .

# Ensure the SQLite data directory exists (ignored by git, created at runtime otherwise)
RUN mkdir -p /app/data /app/exports

# Render/Railway inject $PORT at runtime; default to 8000 for plain `docker run`
ENV PORT=8000
EXPOSE 8000

# Basic container health check (does not call any AI provider)
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request,os; urllib.request.urlopen('http://127.0.0.1:' + os.environ.get('PORT','8000') + '/api/health')" || exit 1

CMD ["sh", "-c", "uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}"]
