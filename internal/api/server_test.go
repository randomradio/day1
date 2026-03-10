package api

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"sort"
	"sync"
	"testing"
	"time"

	"github.com/gin-gonic/gin"

	"day1/internal/config"
	"day1/internal/kernel"
	"day1/internal/mcp"
	"day1/internal/meta"
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

type authMetaStore struct {
	mu       sync.Mutex
	keys     map[string]meta.APIKey
	sessions []meta.Session
	hooks    []meta.HookLog
	traces   []meta.Trace
	comps    []meta.Comparison
}

func newAuthMetaStore() *authMetaStore {
	return &authMetaStore{
		keys:  make(map[string]meta.APIKey),
		hooks: make([]meta.HookLog, 0),
	}
}

func (m *authMetaStore) EnsureMetaSchema(context.Context) error { return nil }

func (m *authMetaStore) LoadMetaState(context.Context) (meta.PersistedState, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	return meta.PersistedState{
		Sessions:    append([]meta.Session(nil), m.sessions...),
		HookLogs:    append([]meta.HookLog(nil), m.hooks...),
		Traces:      append([]meta.Trace(nil), m.traces...),
		Comparisons: append([]meta.Comparison(nil), m.comps...),
	}, nil
}

func (m *authMetaStore) UpsertSession(_ context.Context, session meta.Session) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	for i := range m.sessions {
		if m.sessions[i].ID == session.ID && m.sessions[i].UserID == session.UserID {
			m.sessions[i] = session
			return nil
		}
	}
	m.sessions = append(m.sessions, session)
	return nil
}

func (m *authMetaStore) InsertHookLog(_ context.Context, hook meta.HookLog) (int64, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	hook.Seq = int64(len(m.hooks) + 1)
	m.hooks = append(m.hooks, hook)
	return hook.Seq, nil
}

func (m *authMetaStore) UpsertTrace(_ context.Context, trace meta.Trace) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	for i := range m.traces {
		if m.traces[i].ID == trace.ID {
			m.traces[i] = trace
			return nil
		}
	}
	m.traces = append(m.traces, trace)
	return nil
}

func (m *authMetaStore) UpsertComparison(_ context.Context, comparison meta.Comparison) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	for i := range m.comps {
		if m.comps[i].ID == comparison.ID {
			m.comps[i] = comparison
			return nil
		}
	}
	m.comps = append(m.comps, comparison)
	return nil
}

func (m *authMetaStore) CreateAPIKey(_ context.Context, apiKey meta.APIKey) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	if _, exists := m.keys[apiKey.KeyPrefix]; exists {
		return errors.New("duplicate key prefix")
	}
	m.keys[apiKey.KeyPrefix] = apiKey
	return nil
}

func (m *authMetaStore) ListAPIKeys(_ context.Context, userID string) ([]meta.APIKey, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	out := make([]meta.APIKey, 0)
	for _, item := range m.keys {
		if item.UserID == userID {
			out = append(out, item)
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].CreatedAt.After(out[j].CreatedAt) })
	return out, nil
}

func (m *authMetaStore) GetAPIKeyByPrefix(_ context.Context, keyPrefix string) (*meta.APIKey, error) {
	m.mu.Lock()
	defer m.mu.Unlock()
	item, ok := m.keys[keyPrefix]
	if !ok {
		return nil, nil
	}
	copy := item
	return &copy, nil
}

func (m *authMetaStore) RevokeAPIKey(_ context.Context, keyID string, revokedAt time.Time) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	for prefix, item := range m.keys {
		if item.ID == keyID {
			ts := revokedAt.UTC()
			item.RevokedAt = &ts
			m.keys[prefix] = item
			break
		}
	}
	return nil
}

func (m *authMetaStore) TouchAPIKeyLastUsed(_ context.Context, keyID string, usedAt time.Time) error {
	m.mu.Lock()
	defer m.mu.Unlock()
	for prefix, item := range m.keys {
		if item.ID == keyID {
			ts := usedAt.UTC()
			item.LastUsedAt = &ts
			m.keys[prefix] = item
			break
		}
	}
	return nil
}

func newAuthTestRouter(t *testing.T) *gin.Engine {
	t.Helper()
	cfg := config.Config{
		Port:                 9821,
		AuthEnabled:          true,
		AuthAdminKey:         "admin-secret",
		BootstrapAdminUserID: "admin",
	}
	svc := kernel.NewMemoryService(embedding.NewMockProvider(32), &llm.MockProvider{})
	registry := mcp.NewRegistry(svc)
	server, err := NewServer(cfg, svc, registry, newAuthMetaStore())
	if err != nil {
		t.Fatalf("new auth server: %v", err)
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

func TestAuthRequiresAPIKey(t *testing.T) {
	router := newAuthTestRouter(t)
	res := doRequest(t, router, http.MethodGet, "/api/v1/memories/count?branch=main", nil)
	if res.Code != http.StatusUnauthorized {
		t.Fatalf("expected 401, got %d: %s", res.Code, res.Body.String())
	}
}

func TestAuthAPIKeyIsolation(t *testing.T) {
	router := newAuthTestRouter(t)

	createKey := func(userID string) string {
		resp := doJSONWithHeaders(t, router, http.MethodPost, "/api/v1/auth/keys", map[string]any{
			"user_id": userID,
			"label":   userID + "-key",
		}, map[string]string{"X-Day1-API-Key": "admin-secret"})
		raw, _ := resp["api_key"].(string)
		if raw == "" {
			t.Fatalf("expected api_key for %s", userID)
		}
		return raw
	}

	keyA := createKey("user-a")
	keyB := createKey("user-b")

	created := doJSONWithHeaders(t, router, http.MethodPost, "/api/v1/memories", map[string]any{
		"text": "user a memory",
	}, map[string]string{"X-Day1-API-Key": keyA})
	memID, _ := created["id"].(string)
	if memID == "" {
		t.Fatalf("expected memory id")
	}

	countA := doJSONWithHeaders(t, router, http.MethodGet, "/api/v1/memories/count?branch=main", nil, map[string]string{"X-Day1-API-Key": keyA})
	if int(countA["count"].(float64)) != 1 {
		t.Fatalf("expected user-a count=1, got %v", countA["count"])
	}

	countB := doJSONWithHeaders(t, router, http.MethodGet, "/api/v1/memories/count?branch=main", nil, map[string]string{"X-Day1-API-Key": keyB})
	if int(countB["count"].(float64)) != 0 {
		t.Fatalf("expected user-b count=0, got %v", countB["count"])
	}

	res := doRequestWithHeaders(t, router, http.MethodGet, "/api/v1/memories/"+memID, nil, map[string]string{"X-Day1-API-Key": keyB})
	if res.Code != http.StatusNotFound {
		t.Fatalf("expected 404 when user-b reads user-a memory, got %d", res.Code)
	}
}

func TestRawHookSessionHeader(t *testing.T) {
	router := newAuthTestRouter(t)

	keyResp := doJSONWithHeaders(t, router, http.MethodPost, "/api/v1/auth/keys", map[string]any{
		"user_id": "hook-user",
	}, map[string]string{"X-Day1-API-Key": "admin-secret"})
	key, _ := keyResp["api_key"].(string)
	if key == "" {
		t.Fatalf("expected api key")
	}

	res := doRequestWithHeaders(t, router, http.MethodPost, "/api/v1/ingest/hook", map[string]any{
		"event": "PostToolUse",
	}, map[string]string{
		"X-Day1-API-Key":    key,
		"X-Day1-Session-Id": "sess-hdr",
	})
	if res.Code != http.StatusOK {
		t.Fatalf("expected hook write 200, got %d: %s", res.Code, res.Body.String())
	}

	logs := doJSONWithHeaders(t, router, http.MethodGet, "/api/v1/ingest/hook?session_id=sess-hdr", nil, map[string]string{"X-Day1-API-Key": key})
	if int(logs["count"].(float64)) != 1 {
		t.Fatalf("expected session-scoped hook count=1, got %v", logs["count"])
	}
}

func doJSON(t *testing.T, router http.Handler, method, path string, body map[string]any) map[string]any {
	t.Helper()
	res := doRequestWithHeaders(t, router, method, path, body, nil)
	if res.Code >= 300 {
		t.Fatalf("%s %s returned %d: %s", method, path, res.Code, res.Body.String())
	}
	var out map[string]any
	if err := json.NewDecoder(res.Body).Decode(&out); err != nil {
		t.Fatalf("decode %s %s failed: %v", method, path, err)
	}
	return out
}

func doJSONWithHeaders(t *testing.T, router http.Handler, method, path string, body map[string]any, headers map[string]string) map[string]any {
	t.Helper()
	res := doRequestWithHeaders(t, router, method, path, body, headers)
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
	return doRequestWithHeaders(t, router, method, path, body, nil)
}

func doRequestWithHeaders(t *testing.T, router http.Handler, method, path string, body map[string]any, headers map[string]string) *httptest.ResponseRecorder {
	t.Helper()
	var payload []byte
	if body != nil {
		payload, _ = json.Marshal(body)
	}
	req := httptest.NewRequest(method, path, bytes.NewReader(payload))
	if body != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	for k, v := range headers {
		req.Header.Set(k, v)
	}
	res := httptest.NewRecorder()
	router.ServeHTTP(res, req)
	return res
}
