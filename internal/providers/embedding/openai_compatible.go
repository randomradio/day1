package embedding

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"time"

	"day1/internal/kernel"
)

type openAICompatibleProvider struct {
	apiKey     string
	baseURL    string
	model      string
	dimensions int
	client     *http.Client
}

func newOpenAICompatibleProvider(apiKey, baseURL, model string, dimensions int) (*openAICompatibleProvider, error) {
	if strings.TrimSpace(apiKey) == "" {
		return nil, fmt.Errorf("api key is required")
	}
	if strings.TrimSpace(baseURL) == "" {
		return nil, fmt.Errorf("base url is required")
	}
	if strings.TrimSpace(model) == "" {
		return nil, fmt.Errorf("embedding model is required")
	}
	if dimensions <= 0 {
		dimensions = 1024
	}
	return &openAICompatibleProvider{
		apiKey:     apiKey,
		baseURL:    strings.TrimRight(baseURL, "/"),
		model:      model,
		dimensions: dimensions,
		client:     &http.Client{Timeout: 20 * time.Second},
	}, nil
}

func (p *openAICompatibleProvider) Embed(ctx context.Context, text string) ([]float32, error) {
	if strings.TrimSpace(text) == "" {
		return nil, nil
	}
	payload := map[string]any{
		"model":      p.model,
		"input":      text,
		"dimensions": p.dimensions,
	}
	resp, err := p.do(ctx, payload)
	if err != nil {
		return nil, err
	}
	if len(resp.Data) == 0 {
		return nil, fmt.Errorf("embedding response missing data")
	}
	return resp.Data[0].Embedding, nil
}

func (p *openAICompatibleProvider) EmbedBatch(ctx context.Context, texts []string) ([][]float32, error) {
	if len(texts) == 0 {
		return [][]float32{}, nil
	}
	payload := map[string]any{
		"model":      p.model,
		"input":      texts,
		"dimensions": p.dimensions,
	}
	resp, err := p.do(ctx, payload)
	if err != nil {
		return nil, err
	}
	out := make([][]float32, 0, len(resp.Data))
	for _, d := range resp.Data {
		out = append(out, d.Embedding)
	}
	return out, nil
}

func (p *openAICompatibleProvider) do(ctx context.Context, payload map[string]any) (embeddingResponse, error) {
	body, err := json.Marshal(payload)
	if err != nil {
		return embeddingResponse{}, err
	}
	req, err := http.NewRequestWithContext(ctx, http.MethodPost, p.baseURL+"/embeddings", bytes.NewReader(body))
	if err != nil {
		return embeddingResponse{}, err
	}
	req.Header.Set("Authorization", "Bearer "+p.apiKey)
	req.Header.Set("Content-Type", "application/json")

	res, err := p.client.Do(req)
	if err != nil {
		return embeddingResponse{}, err
	}
	defer res.Body.Close()

	data, err := io.ReadAll(res.Body)
	if err != nil {
		return embeddingResponse{}, err
	}
	if res.StatusCode >= 300 {
		return embeddingResponse{}, fmt.Errorf("embedding api error: status %d body=%s", res.StatusCode, string(data))
	}
	var out embeddingResponse
	if err := json.Unmarshal(data, &out); err != nil {
		return embeddingResponse{}, err
	}
	return out, nil
}

type embeddingResponse struct {
	Data []struct {
		Embedding []float32 `json:"embedding"`
	} `json:"data"`
}

var _ kernel.EmbeddingProvider = (*openAICompatibleProvider)(nil)
