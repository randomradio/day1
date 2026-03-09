package api

import (
	"bytes"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"

	"day1/internal/config"
	"day1/internal/kernel"
	"day1/internal/mcp"
	"day1/internal/providers/embedding"
	"day1/internal/providers/llm"
)

func newTestRouter() *gin.Engine {
	cfg := config.Config{Port: 9821}
	svc := kernel.NewMemoryService(embedding.NewMockProvider(32), &llm.MockProvider{})
	registry := mcp.NewRegistry(svc)
	server, err := NewServer(cfg, svc, registry, nil)
	if err != nil {
		panic(err)
	}
	return server.Router()
}

func TestHealth(t *testing.T) {
	router := newTestRouter()
	res := doRequest(t, router, http.MethodGet, "/health", nil)
	if res.Code != http.StatusOK {
		t.Fatalf("expected 200, got %d", res.Code)
	}
}

func TestMemoryLifecycle(t *testing.T) {
	router := newTestRouter()

	createBody := map[string]any{"text": "test via api", "session_id": "s1"}
	memory := doJSON(t, router, http.MethodPost, "/api/v1/memories", createBody)
	id, _ := memory["id"].(string)
	if id == "" {
		t.Fatalf("expected memory id")
	}

	count := doJSON(t, router, http.MethodGet, "/api/v1/memories/count?branch=main", nil)
	if int(count["count"].(float64)) != 1 {
		t.Fatalf("expected count 1, got %v", count["count"])
	}

	update := map[string]any{"category": "decision"}
	updated := doJSON(t, router, http.MethodPatch, "/api/v1/memories/"+id, update)
	if updated["category"] != "decision" {
		t.Fatalf("expected category decision")
	}

	timeline := doJSON(t, router, http.MethodGet, "/api/v1/memories/timeline?branch=main&limit=10", nil)
	if int(timeline["count"].(float64)) < 1 {
		t.Fatalf("expected timeline entries")
	}

	doJSON(t, router, http.MethodDelete, "/api/v1/memories/"+id, nil)
	count = doJSON(t, router, http.MethodGet, "/api/v1/memories/count?branch=main", nil)
	if int(count["count"].(float64)) != 0 {
		t.Fatalf("expected count 0 after archive, got %v", count["count"])
	}
}

func TestMCPToolsAndInvocation(t *testing.T) {
	router := newTestRouter()

	tools := doJSON(t, router, http.MethodGet, "/api/v1/ingest/mcp-tools", nil)
	if int(tools["count"].(float64)) < 20 {
		t.Fatalf("expected >=20 tools, got %v", tools["count"])
	}

	toolItems, ok := tools["tools"].([]any)
	if !ok {
		t.Fatalf("tools payload malformed")
	}
	names := map[string]struct{}{}
	for _, item := range toolItems {
		entry, _ := item.(map[string]any)
		name, _ := entry["name"].(string)
		names[name] = struct{}{}
	}
	for _, required := range []string{"memory_write", "memory_search", "memory_count"} {
		if _, ok := names[required]; !ok {
			t.Fatalf("missing tool %s", required)
		}
	}

	invocation := doJSON(t, router, http.MethodPost, "/api/v1/ingest/mcp", map[string]any{
		"tool":      "memory_write",
		"arguments": map[string]any{"text": "via mcp", "session_id": "mcp-session"},
	})
	if invocation["tool"] != "memory_write" {
		t.Fatalf("unexpected tool response %v", invocation["tool"])
	}
}

func TestSessionCheckpointAndSummary(t *testing.T) {
	router := newTestRouter()

	checkpoint := doJSON(t, router, http.MethodPost, "/api/v1/sessions/sess-1/checkpoints", map[string]any{
		"category": "decision",
		"text":     "use checkpoint API",
		"branch":   "main",
	})
	if checkpoint["session_id"] != "sess-1" {
		t.Fatalf("unexpected session_id: %v", checkpoint["session_id"])
	}
	if checkpoint["memory_id"] == "" {
		t.Fatalf("expected memory_id in checkpoint response")
	}

	summary := doJSON(t, router, http.MethodGet, "/api/v1/sessions/sess-1/summary", nil)
	if int(summary["memory_count"].(float64)) < 1 {
		t.Fatalf("expected memory_count >= 1, got %v", summary["memory_count"])
	}

	session := doJSON(t, router, http.MethodGet, "/api/v1/sessions/sess-1", nil)
	if _, ok := session["session"].(map[string]any); !ok {
		t.Fatalf("session payload missing session object")
	}
}

func TestTraceCreateExtractAndCompare(t *testing.T) {
	router := newTestRouter()

	doJSON(t, router, http.MethodPost, "/api/v1/ingest/hook", map[string]any{
		"session_id": "trace-session",
		"event":      "PostToolUse",
		"tool":       "Read",
	})

	extracted := doJSON(t, router, http.MethodPost, "/api/v1/traces/extract", map[string]any{
		"session_id": "trace-session",
		"branch":     "main",
	})
	extractedID, _ := extracted["id"].(string)
	if extractedID == "" {
		t.Fatalf("expected extracted trace id")
	}

	created := doJSON(t, router, http.MethodPost, "/api/v1/traces", map[string]any{
		"session_id": "trace-session",
		"branch":     "main",
		"trace_type": "replay",
		"steps": []map[string]any{
			{"index": 1, "event": "user_prompt"},
			{"index": 2, "event": "assistant_reply"},
		},
	})
	createdID, _ := created["id"].(string)
	if createdID == "" {
		t.Fatalf("expected created trace id")
	}

	compare := doJSON(t, router, http.MethodPost, "/api/v1/traces/"+extractedID+"/compare/"+createdID, map[string]any{})
	if compare["verdict"] == "" {
		t.Fatalf("expected comparison verdict")
	}

	list := doJSON(t, router, http.MethodGet, "/api/v1/traces?session_id=trace-session", nil)
	if int(list["count"].(float64)) < 2 {
		t.Fatalf("expected at least two traces, got %v", list["count"])
	}
}

func doJSON(t *testing.T, router http.Handler, method, path string, body map[string]any) map[string]any {
	t.Helper()
	res := doRequest(t, router, method, path, body)
	if res.Code >= 300 {
		t.Fatalf("%s %s returned %d: %s", method, path, res.Code, res.Body.String())
	}
	var out map[string]any
	if err := json.NewDecoder(res.Body).Decode(&out); err != nil {
		t.Fatalf("decode %s %s failed: %v", method, path, err)
	}
	return out
}

func doRequest(t *testing.T, router http.Handler, method, path string, body map[string]any) *httptest.ResponseRecorder {
	t.Helper()
	var payload []byte
	if body != nil {
		payload, _ = json.Marshal(body)
	}
	req := httptest.NewRequest(method, path, bytes.NewReader(payload))
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	res := httptest.NewRecorder()
	router.ServeHTTP(res, req)
	return res
}
