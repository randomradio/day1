package config

import (
	"errors"
	"fmt"
	"os"
	"strconv"
	"strings"
)

// Config contains runtime settings for the Go backend.
type Config struct {
	Port        int
	DatabaseURL string

	EmbeddingProvider string
	EmbeddingModel    string
	EmbeddingDims     int
	EmbeddingBaseURL  string
	EmbeddingAPIKey   string

	LLMProvider string
	LLMModel    string
	LLMBaseURL  string
	LLMAPIKey   string

	OpenAIAPIKey      string
	OpenAIBaseURL     string
	OpenRouterAPIKey  string
	OpenRouterBaseURL string
	AnthropicAPIKey   string
	DoubaoAPIKey      string
	DoubaoBaseURL     string
}

func LoadFromEnv() Config {
	return Config{
		Port:        envInt("BM_PORT", 9821),
		DatabaseURL: envString("BM_DATABASE_URL", ""),

		EmbeddingProvider: strings.ToLower(envString("BM_EMBEDDING_PROVIDER", "mock")),
		EmbeddingModel:    envString("BM_EMBEDDING_MODEL", "text-embedding-3-small"),
		EmbeddingDims:     envInt("BM_EMBEDDING_DIMENSIONS", 1024),
		EmbeddingBaseURL:  envString("BM_EMBEDDING_BASE_URL", ""),
		EmbeddingAPIKey:   envString("BM_EMBEDDING_API_KEY", ""),

		LLMProvider: strings.ToLower(envString("BM_LLM_PROVIDER", "mock")),
		LLMModel:    envString("BM_LLM_MODEL", "gpt-4o-mini"),
		LLMBaseURL:  envString("BM_LLM_BASE_URL", ""),
		LLMAPIKey:   envString("BM_LLM_API_KEY", ""),

		OpenAIAPIKey:      envString("BM_OPENAI_API_KEY", ""),
		OpenAIBaseURL:     envString("BM_OPENAI_BASE_URL", "https://api.openai.com/v1"),
		OpenRouterAPIKey:  envString("BM_OPENROUTER_API_KEY", ""),
		OpenRouterBaseURL: envString("BM_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
		AnthropicAPIKey:   envString("BM_ANTHROPIC_API_KEY", ""),
		DoubaoAPIKey:      envString("BM_DOUBAO_API_KEY", ""),
		DoubaoBaseURL:     envString("BM_DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
	}
}

func (c Config) ValidateBYOK() error {
	if c.Port <= 0 {
		return errors.New("BM_PORT must be > 0")
	}

	switch c.EmbeddingProvider {
	case "", "mock":
	case "openai":
		if c.OpenAIAPIKey == "" {
			return errors.New("BM_EMBEDDING_PROVIDER=openai requires BM_OPENAI_API_KEY")
		}
	case "openrouter":
		if c.OpenRouterAPIKey == "" {
			return errors.New("BM_EMBEDDING_PROVIDER=openrouter requires BM_OPENROUTER_API_KEY")
		}
	case "doubao":
		if c.DoubaoAPIKey == "" {
			return errors.New("BM_EMBEDDING_PROVIDER=doubao requires BM_DOUBAO_API_KEY")
		}
	case "custom":
		if c.EmbeddingAPIKey == "" {
			return errors.New("BM_EMBEDDING_PROVIDER=custom requires BM_EMBEDDING_API_KEY")
		}
		if c.EmbeddingBaseURL == "" {
			return errors.New("BM_EMBEDDING_PROVIDER=custom requires BM_EMBEDDING_BASE_URL")
		}
	default:
		return fmt.Errorf("unsupported BM_EMBEDDING_PROVIDER: %s", c.EmbeddingProvider)
	}

	switch c.LLMProvider {
	case "", "mock":
	case "openai":
		if c.OpenAIAPIKey == "" {
			return errors.New("BM_LLM_PROVIDER=openai requires BM_OPENAI_API_KEY")
		}
	case "anthropic":
		if c.AnthropicAPIKey == "" {
			return errors.New("BM_LLM_PROVIDER=anthropic requires BM_ANTHROPIC_API_KEY")
		}
	case "custom":
		if c.LLMAPIKey == "" {
			return errors.New("BM_LLM_PROVIDER=custom requires BM_LLM_API_KEY")
		}
		if c.LLMBaseURL == "" {
			return errors.New("BM_LLM_PROVIDER=custom requires BM_LLM_BASE_URL")
		}
	default:
		return fmt.Errorf("unsupported BM_LLM_PROVIDER: %s", c.LLMProvider)
	}

	return nil
}

func envString(key, fallback string) string {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	return value
}

func envInt(key string, fallback int) int {
	value := strings.TrimSpace(os.Getenv(key))
	if value == "" {
		return fallback
	}
	parsed, err := strconv.Atoi(value)
	if err != nil {
		return fallback
	}
	return parsed
}
