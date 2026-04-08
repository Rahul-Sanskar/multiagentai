FROM python:3.10-slim

# libgomp1 is required at runtime by faiss/numpy (OpenMP).
# No build-essential needed — binary wheels only.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Layer 1: PyTorch CPU wheel (large, cache-busted only on version change) ───
RUN pip install --no-cache-dir \
    torch==2.3.0 \
    --index-url https://download.pytorch.org/whl/cpu \
    --only-binary=:all:

# ── Layer 2: All other dependencies ──────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir --only-binary=:all: -r requirements.txt

# ── Layer 3: Application source ───────────────────────────────────────────────
COPY . .

RUN mkdir -p /app/data /app/nltk_data

EXPOSE 8080

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
