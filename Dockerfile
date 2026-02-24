# ──────────────────────────────────────────────
# Stage 1: Build the React dashboard
# ──────────────────────────────────────────────
FROM node:22-slim AS dashboard-build

WORKDIR /app/dashboard
COPY dashboard/package.json dashboard/package-lock.json* ./
RUN npm ci
COPY dashboard/ ./
RUN npm run build


# ──────────────────────────────────────────────
# Stage 2: Python backend (target: api)
# ──────────────────────────────────────────────
FROM python:3.11-slim AS api

# Install system deps and uv
RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libffi-dev curl && \
    rm -rf /var/lib/apt/lists/* && \
    curl -LsSf https://astral.sh/uv/install.sh | sh && \
    mv /root/.local/bin/uv /usr/local/bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Copy metadata files FIRST (needed for hatchling to read pyproject.toml)
COPY README.md ./
COPY pyproject.toml ./

# Install dependencies with uv (fast!)
RUN uv pip install --system ".[matrixone]"

# Copy source and install package in editable mode for dev
COPY src/ ./src/
COPY scripts/ ./scripts/
COPY .env.example ./.env.example

RUN uv pip install --system -e .

ENV BM_HOST=0.0.0.0 \
    BM_PORT=8000 \
    BM_EMBEDDING_PROVIDER=mock \
    BM_LOG_LEVEL=DEBUG \
    BM_LOG_FORMAT=text

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["uvicorn", "day1.api.app:app", "--host", "0.0.0.0", "--port", "8000"]


# ──────────────────────────────────────────────
# Stage 3: Nginx dashboard + reverse proxy (target: dashboard)
# ──────────────────────────────────────────────
FROM nginx:alpine AS dashboard

COPY --from=dashboard-build /app/dashboard/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80
