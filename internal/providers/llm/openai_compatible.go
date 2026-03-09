package llm

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
	apiKey  string
	baseURL string
	model   string
	client  *http.Client
}

func newOpenAICompatibleProvider(apiKey, baseURL, model string) (*openAICompatibleProvider, error) {
	if strings.TrimSpace(apiKey) == "" {
		return nil, fmt.Errorf("api key is required")
	}
	if strings.TrimSpace(baseURL) == "" {
		return nil, fmt.Errorf("base url is required")
	}
	if strings.TrimSpace(model) == "" {
		return nil, fmt.Errorf("model is required")
	}
	return &openAICompatibleProvider{
		apiKey:  apiKey,
		baseURL: strings.TrimRight(baseURL, "/"),
		model:   model,
		client:  &http.Client{Timeout: 30 * time.Second},
	}, nil
}

func (p *openAICompatibleProvider) Complete(ctx context.Context, prompt string) (string, error) {
	payload := map[string]any{
		"model":    p.model,
		"messages": []map[string]string{{"role": "user", "content": prompt}},
	}
	body, err := json.Marshal(payload)
	if err != nil {
		return "", err
	}

	req, err := http.NewRequestWithContext(ctx, http.MethodPost, p.baseURL+"/chat/completions", bytes.NewReader(body))
	if err != nil {
		return "", err
	}
	req.Header.Set("Authorization", "Bearer "+p.apiKey)
	req.Header.Set("Content-Type", "application/json")

	res, err := p.client.Do(req)
	if err != nil {
		return "", err
	}
	defer res.Body.Close()

	data, err := io.ReadAll(res.Body)
	if err != nil {
		return "", err
	}
	if res.StatusCode >= 300 {
		return "", fmt.Errorf("llm api error: status %d body=%s", res.StatusCode, string(data))
	}

	var decoded struct {
		Choices []struct {
			Message struct {
				Content string `json:"content"`
			} `json:"message"`
		} `json:"choices"`
	}
	if err := json.Unmarshal(data, &decoded); err != nil {
		return "", err
	}
	if len(decoded.Choices) == 0 {
		return "", nil
	}
	return decoded.Choices[0].Message.Content, nil
}

var _ kernel.LLMProvider = (*openAICompatibleProvider)(nil)
