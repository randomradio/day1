package llm

import (
	"context"

	"day1/internal/kernel"
)

// MockProvider returns empty completions for deterministic tests.
type MockProvider struct{}

func (m *MockProvider) Complete(_ context.Context, _ string) (string, error) {
	return "", nil
}

var _ kernel.LLMProvider = (*MockProvider)(nil)
