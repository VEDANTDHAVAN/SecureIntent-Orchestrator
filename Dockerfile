FROM python:3.11-slim

# Use project root as context
WORKDIR /app

# Copy requirement first for layer caching
COPY apps/api/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code preserving structure
COPY apps/ ./apps/
COPY shared/ ./shared/
COPY db/ ./db/

# Set PYTHONPATH to root so 'shared' and 'db' are discoverable
ENV PYTHONPATH=/app

EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

