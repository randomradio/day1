package embedding

import (
	"fmt"

	"day1/internal/config"
	"day1/internal/kernel"
)

func NewProvider(cfg config.Config) (kernel.EmbeddingProvider, error) {
	switch cfg.EmbeddingProvider {
	case "", "mock":
		return NewMockProvider(cfg.EmbeddingDims), nil
	case "openai":
		return newOpenAICompatibleProvider(cfg.OpenAIAPIKey, cfg.OpenAIBaseURL, cfg.EmbeddingModel, cfg.EmbeddingDims)
	case "openrouter":
		return newOpenAICompatibleProvider(cfg.OpenRouterAPIKey, cfg.OpenRouterBaseURL, cfg.EmbeddingModel, cfg.EmbeddingDims)
	case "custom":
		return newOpenAICompatibleProvider(cfg.EmbeddingAPIKey, cfg.EmbeddingBaseURL, cfg.EmbeddingModel, cfg.EmbeddingDims)
	case "doubao":
		return newOpenAICompatibleProvider(cfg.DoubaoAPIKey, cfg.DoubaoBaseURL, cfg.EmbeddingModel, cfg.EmbeddingDims)
	default:
		return nil, fmt.Errorf("unsupported embedding provider: %s", cfg.EmbeddingProvider)
	}
}
