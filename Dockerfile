FROM python:3.11-slim

# libgomp1 is the only runtime lib needed (OpenMP for faiss/numpy).
# build-essential is NOT needed — we install binary wheels only.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Layer 1: PyTorch CPU wheel (~700 MB, cached unless this line changes) ─────
# Install before requirements.txt so this expensive layer is reused on every
# subsequent push that doesn't change the torch version.
RUN pip install --no-cache-dir \
    torch==2.3.0 \
    --index-url https://download.pytorch.org/whl/cpu \
    --only-binary=:all:

# ── Layer 2: All other dependencies ──────────────────────────────────────────
# --only-binary=:all: ensures pip never falls back to a source/Cython build.
# If a wheel doesn't exist for Python 3.11, pip fails fast with a clear error.
COPY requirements.txt .
RUN pip install --no-cache-dir --only-binary=:all: -r requirements.txt

# ── Layer 3: Application source ───────────────────────────────────────────────
# Copied last so code changes don't invalidate the dependency layers above.
COPY . .

RUN mkdir -p /app/data /app/nltk_data

EXPOSE 8000

# NLTK data is downloaded at runtime inside main.py lifespan — NOT here.
# Downloading at build time adds ~50 MB to the image and slows every build.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
