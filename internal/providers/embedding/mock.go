package embedding

import (
	"context"
	"hash/fnv"

	"day1/internal/kernel"
)

// MockProvider provides deterministic hash-based vectors for tests and local dev.
type MockProvider struct {
	dims int
}

func NewMockProvider(dims int) *MockProvider {
	if dims <= 0 {
		dims = 64
	}
	return &MockProvider{dims: dims}
}

func (p *MockProvider) Embed(_ context.Context, text string) ([]float32, error) {
	vec := make([]float32, p.dims)
	for i := 0; i < p.dims; i++ {
		h := fnv.New64a()
		_, _ = h.Write([]byte(text))
		_, _ = h.Write([]byte{byte(i % 251), byte((i / 251) % 251)})
		vec[i] = float32(h.Sum64()%1000) / 1000.0
	}
	return vec, nil
}

func (p *MockProvider) EmbedBatch(ctx context.Context, texts []string) ([][]float32, error) {
	out := make([][]float32, 0, len(texts))
	for _, text := range texts {
		vec, err := p.Embed(ctx, text)
		if err != nil {
			return nil, err
		}
		out = append(out, vec)
	}
	return out, nil
}

var _ kernel.EmbeddingProvider = (*MockProvider)(nil)
