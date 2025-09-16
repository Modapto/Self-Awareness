# ---- Stage 1: Build dependencies ----
FROM python:3.11-slim AS builder

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends gcc build-essential && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --user --no-cache-dir -r requirements.txt

# ---- Stage 2: Final image ----
FROM python:3.11-slim

WORKDIR /app

ENV PATH="/root/.local/bin:$PATH"

# Copy only necessary files
COPY --from=builder /root/.local /root/.local
COPY . .

EXPOSE 8000

# Environment variables for logging
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Default command with logging and reload for development
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "info", "--access-log"]
