package main

import (
	"context"
	"log"
	"net/http"
	"time"

	"day1/internal/api"
	"day1/internal/config"
	"day1/internal/kernel"
	"day1/internal/mcp"
	"day1/internal/providers/embedding"
	"day1/internal/providers/llm"
	"day1/internal/storage"
)

func main() {
	cfg := config.LoadFromEnv()
	if err := cfg.ValidateBYOK(); err != nil {
		log.Fatalf("config validation failed: %v", err)
	}

	embedder, err := embedding.NewProvider(cfg)
	if err != nil {
		log.Fatalf("embedding provider init failed: %v", err)
	}

	llmProvider, err := llm.NewProvider(cfg)
	if err != nil {
		log.Fatalf("llm provider init failed: %v", err)
	}

	var memoryKernel kernel.MemoryKernel
	var sqlStore *storage.MySQLStore
	if cfg.DatabaseURL != "" {
		store, err := storage.NewMySQLStoreFromURL(cfg.DatabaseURL)
		if err != nil {
			log.Fatalf("storage init failed: %v", err)
		}
		sqlStore = store
		defer func() { _ = sqlStore.Close() }()
		sqlKernel, err := kernel.NewMemoryServiceWithStore(context.Background(), embedder, llmProvider, store)
		if err != nil {
			log.Fatalf("kernel store bootstrap failed: %v", err)
		}
		memoryKernel = sqlKernel
		log.Printf("day1-go using SQL persistence backend")
	} else {
		memoryKernel = kernel.NewMemoryService(embedder, llmProvider)
		log.Printf("day1-go using in-memory backend (set DAY1_DATABASE_URL for SQL persistence)")
	}
	registry := mcp.NewRegistry(memoryKernel)
	var metadataStore api.MetadataStore
	if sqlStore != nil {
		metadataStore = sqlStore
	}
	server, err := api.NewServer(cfg, memoryKernel, registry, metadataStore)
	if err != nil {
		log.Fatalf("api server bootstrap failed: %v", err)
	}

	httpServer := &http.Server{
		Addr:              ":" + itoa(cfg.Port),
		Handler:           server.Router(),
		ReadHeaderTimeout: 10 * time.Second,
		ReadTimeout:       20 * time.Second,
		WriteTimeout:      20 * time.Second,
		IdleTimeout:       60 * time.Second,
	}

	log.Printf("day1-go server listening on %s", httpServer.Addr)
	if err := httpServer.ListenAndServe(); err != nil && err != http.ErrServerClosed {
		log.Fatalf("server failed: %v", err)
	}
}

func itoa(v int) string {
	if v == 0 {
		return "0"
	}
	negative := false
	if v < 0 {
		negative = true
		v = -v
	}
	buf := make([]byte, 0, 12)
	for v > 0 {
		buf = append(buf, byte('0'+v%10))
		v /= 10
	}
	if negative {
		buf = append(buf, '-')
	}
	for i, j := 0, len(buf)-1; i < j; i, j = i+1, j-1 {
		buf[i], buf[j] = buf[j], buf[i]
	}
	return string(buf)
}
