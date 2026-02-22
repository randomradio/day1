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

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc libffi-dev && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps (cache-friendly layer)
COPY pyproject.toml ./
RUN pip install --no-cache-dir ".[matrixone]"

# Copy source and install package
COPY src/ ./src/
RUN pip install --no-cache-dir -e .

COPY scripts/ ./scripts/
COPY .env.example ./.env.example

ENV BM_HOST=0.0.0.0
ENV BM_PORT=8000
ENV BM_EMBEDDING_PROVIDER=mock

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
