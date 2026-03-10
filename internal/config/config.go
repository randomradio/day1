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

	AuthEnabled          bool
	AuthAdminKey         string
	BootstrapAdminUserID string

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
		Port:                 envInt("DAY1_PORT", 9821),
		DatabaseURL:          envString("DAY1_DATABASE_URL", ""),
		AuthEnabled:          envBool("DAY1_AUTH_ENABLED", false),
		AuthAdminKey:         envString("DAY1_AUTH_ADMIN_KEY", ""),
		BootstrapAdminUserID: envString("DAY1_BOOTSTRAP_ADMIN_USER_ID", "admin"),

		EmbeddingProvider: strings.ToLower(envString("DAY1_EMBEDDING_PROVIDER", "mock")),
		EmbeddingModel:    envString("DAY1_EMBEDDING_MODEL", "text-embedding-3-small"),
		EmbeddingDims:     envInt("DAY1_EMBEDDING_DIMENSIONS", 1024),
		EmbeddingBaseURL:  envString("DAY1_EMBEDDING_BASE_URL", ""),
		EmbeddingAPIKey:   envString("DAY1_EMBEDDING_API_KEY", ""),

		LLMProvider: strings.ToLower(envString("DAY1_LLM_PROVIDER", "mock")),
		LLMModel:    envString("DAY1_LLM_MODEL", "gpt-4o-mini"),
		LLMBaseURL:  envString("DAY1_LLM_BASE_URL", ""),
		LLMAPIKey:   envString("DAY1_LLM_API_KEY", ""),

		OpenAIAPIKey:      envString("DAY1_OPENAI_API_KEY", ""),
		OpenAIBaseURL:     envString("DAY1_OPENAI_BASE_URL", "https://api.openai.com/v1"),
		OpenRouterAPIKey:  envString("DAY1_OPENROUTER_API_KEY", ""),
		OpenRouterBaseURL: envString("DAY1_OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
		AnthropicAPIKey:   envString("DAY1_ANTHROPIC_API_KEY", ""),
		DoubaoAPIKey:      envString("DAY1_DOUBAO_API_KEY", ""),
		DoubaoBaseURL:     envString("DAY1_DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"),
	}
}

func (c Config) ValidateBYOK() error {
	if c.Port <= 0 {
		return errors.New("DAY1_PORT must be > 0")
	}
	if c.AuthEnabled {
		if strings.TrimSpace(c.DatabaseURL) == "" {
			return errors.New("DAY1_AUTH_ENABLED=true requires DAY1_DATABASE_URL")
		}
		if strings.TrimSpace(c.AuthAdminKey) == "" {
			return errors.New("DAY1_AUTH_ENABLED=true requires DAY1_AUTH_ADMIN_KEY")
		}
		if strings.TrimSpace(c.BootstrapAdminUserID) == "" {
			return errors.New("DAY1_AUTH_ENABLED=true requires DAY1_BOOTSTRAP_ADMIN_USER_ID")
		}
	}

	switch c.EmbeddingProvider {
	case "", "mock":
	case "openai":
		if c.OpenAIAPIKey == "" {
			return errors.New("DAY1_EMBEDDING_PROVIDER=openai requires DAY1_OPENAI_API_KEY")
		}
	case "openrouter":
		if c.OpenRouterAPIKey == "" {
			return errors.New("DAY1_EMBEDDING_PROVIDER=openrouter requires DAY1_OPENROUTER_API_KEY")
		}
	case "doubao":
		if c.DoubaoAPIKey == "" {
			return errors.New("DAY1_EMBEDDING_PROVIDER=doubao requires DAY1_DOUBAO_API_KEY")
		}
	case "custom":
		if c.EmbeddingAPIKey == "" {
			return errors.New("DAY1_EMBEDDING_PROVIDER=custom requires DAY1_EMBEDDING_API_KEY")
		}
		if c.EmbeddingBaseURL == "" {
			return errors.New("DAY1_EMBEDDING_PROVIDER=custom requires DAY1_EMBEDDING_BASE_URL")
		}
	default:
		return fmt.Errorf("unsupported DAY1_EMBEDDING_PROVIDER: %s", c.EmbeddingProvider)
	}

	switch c.LLMProvider {
	case "", "mock":
	case "openai":
		if c.OpenAIAPIKey == "" {
			return errors.New("DAY1_LLM_PROVIDER=openai requires DAY1_OPENAI_API_KEY")
		}
	case "anthropic":
		if c.AnthropicAPIKey == "" {
			return errors.New("DAY1_LLM_PROVIDER=anthropic requires DAY1_ANTHROPIC_API_KEY")
		}
	case "custom":
		if c.LLMAPIKey == "" {
			return errors.New("DAY1_LLM_PROVIDER=custom requires DAY1_LLM_API_KEY")
		}
		if c.LLMBaseURL == "" {
			return errors.New("DAY1_LLM_PROVIDER=custom requires DAY1_LLM_BASE_URL")
		}
	default:
		return fmt.Errorf("unsupported DAY1_LLM_PROVIDER: %s", c.LLMProvider)
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

func envBool(key string, fallback bool) bool {
	value := strings.TrimSpace(strings.ToLower(os.Getenv(key)))
	if value == "" {
		return fallback
	}
	switch value {
	case "1", "true", "yes", "on":
		return true
	case "0", "false", "no", "off":
		return false
	default:
		return fallback
	}
}
