FROM python:3.11-slim

# Install system deps needed by some Python libs
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy root-level requirements (covers all modules: api, engines, sandbox, tools, agents)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy all source modules
COPY apps/      ./apps/
COPY shared/    ./shared/
COPY db/        ./db/
COPY agents/    ./agents/
COPY engines/   ./engines/
COPY sandbox/   ./sandbox/
COPY tools/     ./tools/

# PYTHONPATH ensures all modules (shared, db, engines, etc.) are importable
ENV PYTHONPATH=/app

EXPOSE 8000

# Dev: --reload watches for code changes inside the container (via volume mount)
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]
