FROM python:3.10-slim

# libgomp1 required at runtime by faiss/numpy (OpenMP).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Layer 1: torch CPU wheel — large (~700MB), cached unless version changes.
# Installed separately so code/dep changes don't re-download torch every build.
RUN pip install --no-cache-dir \
    torch==2.3.0 \
    --index-url https://download.pytorch.org/whl/cpu \
    --only-binary=:all:

# Layer 2: remaining dependencies (all binary wheels, no compilation).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Layer 3: app source — last so code changes don't bust dep layers.
COPY . .

RUN mkdir -p /app/data /app/nltk_data

EXPOSE 8080

CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8080}"]
