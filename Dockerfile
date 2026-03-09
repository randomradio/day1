# Day1 backend containers (Go backend only)

FROM golang:1.24 AS go-base
WORKDIR /app
COPY go.mod go.sum ./
RUN go mod download

FROM go-base AS api-builder
COPY cmd ./cmd
COPY internal ./internal
RUN CGO_ENABLED=0 GOOS=linux go build -o /out/day1-api ./cmd/day1-api && \
    CGO_ENABLED=0 GOOS=linux go build -o /out/day1 ./cmd/day1

FROM debian:bookworm-slim AS api
RUN apt-get update && \
    apt-get install -y --no-install-recommends ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=api-builder /out/day1-api /usr/local/bin/day1-api
COPY --from=api-builder /out/day1 /usr/local/bin/day1
EXPOSE 9821
HEALTHCHECK --interval=15s --timeout=3s --start-period=8s --retries=3 \
    CMD curl -fsS http://localhost:9821/health >/dev/null || exit 1
CMD ["day1-api"]

FROM go-base AS api-dev
COPY . .
EXPOSE 9821
CMD ["go", "run", "./cmd/day1-api"]
