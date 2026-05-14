# syntax=docker/dockerfile:1.7

# ── Stage 1: build the Vite frontend ────────────────────────────────────────
# Pinned to Node 20 (matches the dev environment). The build emits
# frontend/dist/ which the runtime stage copies in.
FROM node:20-alpine AS frontend-build

WORKDIR /app/frontend

# Install deps using the lockfile so the build is deterministic.
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund

# Copy the rest of the frontend source AFTER deps so dep installs cache well.
COPY frontend/ ./
RUN npm run build


# ── Stage 2: Python runtime ────────────────────────────────────────────────
# python:3.12-slim is the smallest current-Python image with apt. Backend pins
# to >=3.10 in pyproject.toml; 3.12 is comfortably inside that floor.
FROM python:3.12-slim AS runtime

# uv would be lighter but adds a dep — pip + venv is plenty for a single-
# container service.
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first (long, cache-friendly layer). Use the project's
# own pyproject.toml so adding a backend dep flows through automatically.
COPY pyproject.toml ./
RUN pip install \
      "fastapi>=0.115.0" \
      "uvicorn[standard]>=0.32.0" \
      "python-dotenv>=1.0.0" \
      "httpx>=0.27.0" \
      "pydantic>=2.9.0"

# Backend source.
COPY backend/ ./backend/

# Brief lives at the repo root; mounted via context.py's BRIEF_PATH lookup.
COPY RAI_Council_Brief.md ./RAI_Council_Brief.md

# Frontend bundle from the builder stage. main.py's static mount activates
# whenever frontend/dist/ exists, so just being in the image is enough.
COPY --from=frontend-build /app/frontend/dist ./frontend/dist

# `data/` (verdict log + conversations) is gitignored and lives outside the
# image — Coolify mounts a persistent volume at /app/data so chat history and
# the verdicts.db survive container rebuilds.
RUN mkdir -p /app/data/conversations

EXPOSE 8001

# Single worker on purpose: the in-memory balance cache (backend/balance.py)
# and the streaming endpoint's per-request state are not shared across
# workers. For personal-use traffic, one worker is plenty.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8001", "--workers", "1"]
