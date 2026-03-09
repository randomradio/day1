package config

import (
	"os"
	"testing"
)

func TestValidateBYOKMockPasses(t *testing.T) {
	t.Setenv("BM_EMBEDDING_PROVIDER", "mock")
	t.Setenv("BM_LLM_PROVIDER", "mock")
	cfg := LoadFromEnv()
	if err := cfg.ValidateBYOK(); err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
}

func TestValidateBYOKOpenAIEmbeddingRequiresKey(t *testing.T) {
	unset(t, "BM_OPENAI_API_KEY")
	t.Setenv("BM_EMBEDDING_PROVIDER", "openai")
	t.Setenv("BM_LLM_PROVIDER", "mock")
	cfg := LoadFromEnv()
	if err := cfg.ValidateBYOK(); err == nil {
		t.Fatalf("expected validation error for missing BM_OPENAI_API_KEY")
	}
}

func TestValidateBYOKCustomLLMRequiresKeyAndURL(t *testing.T) {
	unset(t, "BM_LLM_API_KEY")
	unset(t, "BM_LLM_BASE_URL")
	t.Setenv("BM_EMBEDDING_PROVIDER", "mock")
	t.Setenv("BM_LLM_PROVIDER", "custom")
	cfg := LoadFromEnv()
	if err := cfg.ValidateBYOK(); err == nil {
		t.Fatalf("expected validation error for missing custom llm credentials")
	}

	t.Setenv("BM_LLM_API_KEY", "k")
	t.Setenv("BM_LLM_BASE_URL", "https://example.com/v1")
	cfg = LoadFromEnv()
	if err := cfg.ValidateBYOK(); err != nil {
		t.Fatalf("expected no error after setting values, got %v", err)
	}
}

func unset(t *testing.T, key string) {
	t.Helper()
	if err := os.Unsetenv(key); err != nil {
		t.Fatalf("unset %s: %v", key, err)
	}
}
