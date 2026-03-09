package llm

import (
	"fmt"

	"day1/internal/config"
	"day1/internal/kernel"
)

func NewProvider(cfg config.Config) (kernel.LLMProvider, error) {
	switch cfg.LLMProvider {
	case "", "mock":
		return &MockProvider{}, nil
	case "openai":
		return newOpenAICompatibleProvider(cfg.OpenAIAPIKey, cfg.OpenAIBaseURL, cfg.LLMModel)
	case "anthropic":
		return newOpenAICompatibleProvider(cfg.AnthropicAPIKey, "https://api.anthropic.com/v1", cfg.LLMModel)
	case "custom":
		return newOpenAICompatibleProvider(cfg.LLMAPIKey, cfg.LLMBaseURL, cfg.LLMModel)
	default:
		return nil, fmt.Errorf("unsupported llm provider: %s", cfg.LLMProvider)
	}
}
