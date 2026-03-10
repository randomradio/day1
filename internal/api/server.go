package api

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"errors"
	"fmt"
	"math"
	"net/http"
	"sort"
	"strconv"
	"strings"
	"sync"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/google/uuid"

	"day1/internal/config"
	"day1/internal/kernel"
	"day1/internal/mcp"
	"day1/internal/meta"
)

// MetadataStore persists API-layer session/trace/hook/comparison records.
type MetadataStore interface {
	EnsureMetaSchema(ctx context.Context) error
	LoadMetaState(ctx context.Context) (meta.PersistedState, error)
	UpsertSession(ctx context.Context, session meta.Session) error
	InsertHookLog(ctx context.Context, hook meta.HookLog) (int64, error)
	UpsertTrace(ctx context.Context, trace meta.Trace) error
	UpsertComparison(ctx context.Context, comparison meta.Comparison) error
	CreateAPIKey(ctx context.Context, apiKey meta.APIKey) error
	ListAPIKeys(ctx context.Context, userID string) ([]meta.APIKey, error)
	GetAPIKeyByPrefix(ctx context.Context, keyPrefix string) (*meta.APIKey, error)
	RevokeAPIKey(ctx context.Context, keyID string, revokedAt time.Time) error
	TouchAPIKeyLastUsed(ctx context.Context, keyID string, usedAt time.Time) error
}

type sessionState struct {
	ID          string     `json:"id"`
	UserID      string     `json:"user_id,omitempty"`
	BranchName  string     `json:"branch_name"`
	Status      string     `json:"status"`
	StartedAt   time.Time  `json:"started_at"`
	EndedAt     *time.Time `json:"ended_at,omitempty"`
	MemoryCount int        `json:"memory_count"`
	TraceCount  int        `json:"trace_count"`
	HookCount   int        `json:"hook_count"`
}

type traceState struct {
	ID              string           `json:"id"`
	UserID          string           `json:"user_id,omitempty"`
	SessionID       string           `json:"session_id,omitempty"`
	Branch          string           `json:"branch"`
	TraceType       string           `json:"trace_type"`
	ParentTraceID   string           `json:"parent_trace_id,omitempty"`
	SkillID         string           `json:"skill_id,omitempty"`
	TaskDescription string           `json:"task_description,omitempty"`
	Steps           []map[string]any `json:"steps"`
	Metadata        map[string]any   `json:"metadata,omitempty"`
	CreatedAt       time.Time        `json:"created_at"`
}

type comparisonState struct {
	ID              string             `json:"id"`
	UserID          string             `json:"user_id,omitempty"`
	TraceAID        string             `json:"trace_a_id"`
	TraceBID        string             `json:"trace_b_id"`
	SkillID         string             `json:"skill_id,omitempty"`
	DimensionScores map[string]float64 `json:"dimension_scores"`
	Verdict         string             `json:"verdict"`
	Insights        map[string]any     `json:"insights,omitempty"`
	CreatedAt       time.Time          `json:"created_at"`
}

type Server struct {
	cfg      config.Config
	kernel   kernel.MemoryKernel
	registry *mcp.Registry
	meta     MetadataStore

	hooksMu sync.RWMutex
	hooks   []map[string]any

	metaMu      sync.RWMutex
	sessions    map[string]*sessionState
	traces      map[string]traceState
	comparisons []comparisonState
}

type apiPrincipal struct {
	UserID  string
	KeyID   string
	IsAdmin bool
}

const principalContextKey = "day1.principal"

func NewServer(cfg config.Config, k kernel.MemoryKernel, registry *mcp.Registry, metadataStore MetadataStore) (*Server, error) {
	if cfg.AuthEnabled && metadataStore == nil {
		return nil, fmt.Errorf("auth requires metadata store backing")
	}
	s := &Server{
		cfg:         cfg,
		kernel:      k,
		registry:    registry,
		meta:        metadataStore,
		hooks:       make([]map[string]any, 0),
		sessions:    make(map[string]*sessionState),
		traces:      make(map[string]traceState),
		comparisons: make([]comparisonState, 0),
	}

	if s.meta != nil {
		ctx := context.Background()
		if err := s.meta.EnsureMetaSchema(ctx); err != nil {
			return nil, fmt.Errorf("ensure metadata schema: %w", err)
		}
		state, err := s.meta.LoadMetaState(ctx)
		if err != nil {
			return nil, fmt.Errorf("load metadata state: %w", err)
		}
		s.loadMetaState(state)
	}

	return s, nil
}

func (s *Server) loadMetaState(state meta.PersistedState) {
	s.metaMu.Lock()
	for _, item := range state.Sessions {
		copy := item
		s.sessions[sessionKey(item.UserID, item.ID)] = &sessionState{
			ID:          copy.ID,
			UserID:      copy.UserID,
			BranchName:  copy.BranchName,
			Status:      copy.Status,
			StartedAt:   copy.StartedAt,
			EndedAt:     copy.EndedAt,
			MemoryCount: copy.MemoryCount,
			TraceCount:  copy.TraceCount,
			HookCount:   copy.HookCount,
		}
	}
	for _, item := range state.Traces {
		s.traces[item.ID] = traceState{
			ID:              item.ID,
			UserID:          item.UserID,
			SessionID:       item.SessionID,
			Branch:          item.BranchName,
			TraceType:       item.TraceType,
			ParentTraceID:   item.ParentTraceID,
			SkillID:         item.SkillID,
			TaskDescription: item.TaskDescription,
			Steps:           item.Steps,
			Metadata:        item.Metadata,
			CreatedAt:       item.CreatedAt,
		}
	}
	for _, item := range state.Comparisons {
		s.comparisons = append(s.comparisons, comparisonState{
			ID:              item.ID,
			UserID:          item.UserID,
			TraceAID:        item.TraceAID,
			TraceBID:        item.TraceBID,
			SkillID:         item.SkillID,
			DimensionScores: item.DimensionScores,
			Verdict:         item.Verdict,
			Insights:        item.Insights,
			CreatedAt:       item.CreatedAt,
		})
	}
	s.metaMu.Unlock()

	s.hooksMu.Lock()
	for _, hook := range state.HookLogs {
		s.hooks = append(s.hooks, map[string]any{
			"seq":        hook.Seq,
			"event":      hook.Event,
			"user_id":    hook.UserID,
			"session_id": hook.SessionID,
			"payload":    hook.Payload,
			"created_at": hook.CreatedAt,
		})
	}
	s.hooksMu.Unlock()
}

func (s *Server) Router() *gin.Engine {
	r := gin.New()
	r.Use(gin.Recovery(), gin.Logger())

	r.GET("/health", func(c *gin.Context) {
		c.JSON(http.StatusOK, gin.H{"status": "ok", "version": "3.2.0-go"})
	})

	v1 := r.Group("/api/v1")
	if s.cfg.AuthEnabled {
		v1.Use(s.authMiddleware())
	} else {
		v1.Use(s.anonymousPrincipalMiddleware())
	}
	{
		v1.POST("/auth/keys", s.handleAuthKeyCreate)
		v1.GET("/auth/keys", s.handleAuthKeyList)
		v1.POST("/auth/keys/:key_id/revoke", s.handleAuthKeyRevoke)

		v1.POST("/memories", s.handleMemoryWrite)
		v1.GET("/memories/timeline", s.handleMemoryTimeline)
		v1.GET("/memories/count", s.handleMemoryCount)
		v1.GET("/memories/:memory_id", s.handleMemoryGet)
		v1.PATCH("/memories/:memory_id", s.handleMemoryUpdate)
		v1.DELETE("/memories/:memory_id", s.handleMemoryArchive)
		v1.POST("/memories/batch", s.handleMemoryBatchWrite)
		v1.DELETE("/memories/batch", s.handleMemoryBatchArchive)
		v1.POST("/memories/:memory_id/relations", s.handleRelationCreate)
		v1.GET("/memories/:memory_id/relations", s.handleRelationList)
		v1.GET("/memories/:memory_id/graph", s.handleMemoryGraph)
		v1.DELETE("/relations/:relation_id", s.handleRelationDelete)

		v1.GET("/ingest/mcp-tools", s.handleMCPTools)
		v1.POST("/ingest/mcp", s.handleMCPInvoke)
		v1.POST("/ingest/mcp-tools/:tool_name", s.handleMCPInvokePath)
		v1.POST("/ingest/claude-hook", s.handleClaudeHook)
		v1.POST("/ingest/hook", s.handleRawHook)
		v1.GET("/ingest/hook", s.handleListHooks)

		v1.GET("/sessions", s.handleSessionsList)
		v1.GET("/sessions/:session_id", s.handleSessionGet)
		v1.GET("/sessions/:session_id/summary", s.handleSessionSummary)
		v1.POST("/sessions/:session_id/checkpoints", s.handleSessionCheckpoint)

		v1.GET("/traces", s.handleTraceList)
		v1.GET("/traces/:trace_id", s.handleTraceGet)
		v1.POST("/traces", s.handleTraceCreate)
		v1.POST("/traces/extract", s.handleTraceExtract)
		v1.POST("/traces/:trace_a_id/compare/:trace_b_id", s.handleTraceCompare)
	}

	return r
}

func (s *Server) anonymousPrincipalMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		principal := apiPrincipal{}
		c.Set(principalContextKey, principal)
		ctx := kernel.WithUserID(c.Request.Context(), principal.UserID)
		c.Request = c.Request.WithContext(ctx)
		c.Next()
	}
}

func (s *Server) authMiddleware() gin.HandlerFunc {
	return func(c *gin.Context) {
		key := extractAPIKeyFromRequest(c.Request)
		if key == "" {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "missing API key"})
			c.Abort()
			return
		}

		principal := apiPrincipal{}
		if subtle.ConstantTimeCompare([]byte(key), []byte(s.cfg.AuthAdminKey)) == 1 {
			principal = apiPrincipal{
				UserID:  s.cfg.BootstrapAdminUserID,
				KeyID:   "admin",
				IsAdmin: true,
			}
		} else {
			prefix, ok := extractAPIKeyPrefix(key)
			if !ok {
				c.JSON(http.StatusUnauthorized, gin.H{"error": "invalid API key"})
				c.Abort()
				return
			}
			apiKey, err := s.meta.GetAPIKeyByPrefix(c.Request.Context(), prefix)
			if err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
				c.Abort()
				return
			}
			if apiKey == nil || apiKey.RevokedAt != nil {
				c.JSON(http.StatusUnauthorized, gin.H{"error": "invalid API key"})
				c.Abort()
				return
			}
			expectedHash := hashAPIKey(key)
			if subtle.ConstantTimeCompare([]byte(expectedHash), []byte(apiKey.KeyHash)) != 1 {
				c.JSON(http.StatusUnauthorized, gin.H{"error": "invalid API key"})
				c.Abort()
				return
			}
			principal = apiPrincipal{
				UserID: apiKey.UserID,
				KeyID:  apiKey.ID,
			}
			if err := s.meta.TouchAPIKeyLastUsed(c.Request.Context(), apiKey.ID, time.Now().UTC()); err != nil {
				c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
				c.Abort()
				return
			}
		}

		if strings.TrimSpace(principal.UserID) == "" {
			c.JSON(http.StatusUnauthorized, gin.H{"error": "invalid API key principal"})
			c.Abort()
			return
		}

		c.Set(principalContextKey, principal)
		ctx := kernel.WithUserID(c.Request.Context(), principal.UserID)
		c.Request = c.Request.WithContext(ctx)
		c.Next()
	}
}

func extractAPIKeyFromRequest(r *http.Request) string {
	if r == nil {
		return ""
	}
	if header := strings.TrimSpace(r.Header.Get("X-Day1-API-Key")); header != "" {
		return header
	}
	auth := strings.TrimSpace(r.Header.Get("Authorization"))
	if len(auth) >= 7 && strings.EqualFold(auth[:7], "Bearer ") {
		return strings.TrimSpace(auth[7:])
	}
	return ""
}

func (s *Server) currentPrincipal(c *gin.Context) apiPrincipal {
	if c == nil {
		return apiPrincipal{}
	}
	raw, ok := c.Get(principalContextKey)
	if !ok {
		return apiPrincipal{}
	}
	principal, ok := raw.(apiPrincipal)
	if !ok {
		return apiPrincipal{}
	}
	return principal
}

func (s *Server) currentUserID(c *gin.Context) string {
	principal := s.currentPrincipal(c)
	return strings.TrimSpace(principal.UserID)
}

func (s *Server) handleAuthKeyCreate(c *gin.Context) {
	if !s.cfg.AuthEnabled {
		c.JSON(http.StatusBadRequest, gin.H{"error": "auth is disabled"})
		return
	}
	principal := s.currentPrincipal(c)
	if !principal.IsAdmin {
		c.JSON(http.StatusForbidden, gin.H{"error": "admin key required"})
		return
	}

	var payload struct {
		UserID string   `json:"user_id"`
		Label  string   `json:"label"`
		Scopes []string `json:"scopes"`
	}
	if err := c.ShouldBindJSON(&payload); err != nil {
		writeError(c, fmt.Errorf("%w: %v", kernel.ErrInvalidInput, err))
		return
	}
	userID := strings.TrimSpace(payload.UserID)
	if userID == "" {
		writeError(c, fmt.Errorf("%w: user_id is required", kernel.ErrInvalidInput))
		return
	}
	label := strings.TrimSpace(payload.Label)
	scopes := sanitizeScopes(payload.Scopes)
	now := time.Now().UTC()

	const maxAttempts = 4
	var (
		plainKey string
		record   meta.APIKey
		err      error
	)
	for i := 0; i < maxAttempts; i++ {
		plainKey, record, err = newAPIKeyRecord(userID, label, scopes, now)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		err = s.meta.CreateAPIKey(c.Request.Context(), record)
		if err == nil {
			break
		}
		if !strings.Contains(strings.ToLower(err.Error()), "duplicate") {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
	}
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}

	c.JSON(http.StatusCreated, gin.H{
		"id":         record.ID,
		"user_id":    record.UserID,
		"label":      record.Label,
		"scopes":     record.Scopes,
		"key_prefix": record.KeyPrefix,
		"created_at": record.CreatedAt,
		"api_key":    plainKey,
	})
}

func (s *Server) handleAuthKeyList(c *gin.Context) {
	if !s.cfg.AuthEnabled {
		c.JSON(http.StatusBadRequest, gin.H{"error": "auth is disabled"})
		return
	}
	principal := s.currentPrincipal(c)
	queryUserID := strings.TrimSpace(c.Query("user_id"))
	userID := principal.UserID
	if principal.IsAdmin {
		if queryUserID != "" {
			userID = queryUserID
		}
	} else if queryUserID != "" && queryUserID != principal.UserID {
		c.JSON(http.StatusForbidden, gin.H{"error": "forbidden"})
		return
	}

	keys, err := s.meta.ListAPIKeys(c.Request.Context(), userID)
	if err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	items := make([]map[string]any, 0, len(keys))
	for _, key := range keys {
		items = append(items, map[string]any{
			"id":           key.ID,
			"user_id":      key.UserID,
			"label":        key.Label,
			"scopes":       key.Scopes,
			"key_prefix":   key.KeyPrefix,
			"created_at":   key.CreatedAt,
			"last_used_at": key.LastUsedAt,
			"revoked_at":   key.RevokedAt,
		})
	}
	c.JSON(http.StatusOK, gin.H{"keys": items, "count": len(items)})
}

func (s *Server) handleAuthKeyRevoke(c *gin.Context) {
	if !s.cfg.AuthEnabled {
		c.JSON(http.StatusBadRequest, gin.H{"error": "auth is disabled"})
		return
	}
	keyID := strings.TrimSpace(c.Param("key_id"))
	if keyID == "" {
		writeError(c, fmt.Errorf("%w: key_id is required", kernel.ErrInvalidInput))
		return
	}

	principal := s.currentPrincipal(c)
	if !principal.IsAdmin {
		owned, err := s.meta.ListAPIKeys(c.Request.Context(), principal.UserID)
		if err != nil {
			c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
			return
		}
		allowed := false
		for _, item := range owned {
			if item.ID == keyID {
				allowed = true
				break
			}
		}
		if !allowed {
			c.JSON(http.StatusNotFound, gin.H{"error": "api key not found"})
			return
		}
	}

	if err := s.meta.RevokeAPIKey(c.Request.Context(), keyID, time.Now().UTC()); err != nil {
		c.JSON(http.StatusInternalServerError, gin.H{"error": err.Error()})
		return
	}
	c.JSON(http.StatusOK, gin.H{"revoked": true, "key_id": keyID})
}

func sanitizeScopes(scopes []string) []string {
	if len(scopes) == 0 {
		return []string{"memory:*"}
	}
	out := make([]string, 0, len(scopes))
	seen := map[string]struct{}{}
	for _, item := range scopes {
		scoped := strings.TrimSpace(item)
		if scoped == "" {
			continue
		}
		if _, ok := seen[scoped]; ok {
			continue
		}
		seen[scoped] = struct{}{}
		out = append(out, scoped)
	}
	if len(out) == 0 {
		return []string{"memory:*"}
	}
	return out
}

func newAPIKeyRecord(userID, label string, scopes []string, now time.Time) (string, meta.APIKey, error) {
	prefixBytes := make([]byte, 6)
	if _, err := rand.Read(prefixBytes); err != nil {
		return "", meta.APIKey{}, fmt.Errorf("generate key prefix: %w", err)
	}
	secretBytes := make([]byte, 24)
	if _, err := rand.Read(secretBytes); err != nil {
		return "", meta.APIKey{}, fmt.Errorf("generate key secret: %w", err)
	}
	prefix := hex.EncodeToString(prefixBytes)
	secret := hex.EncodeToString(secretBytes)
	plain := "day1_" + prefix + "_" + secret
	record := meta.APIKey{
		ID:        uuid.NewString(),
		KeyPrefix: prefix,
		KeyHash:   hashAPIKey(plain),
		UserID:    userID,
		Label:     label,
		Scopes:    scopes,
		CreatedAt: now,
	}
	return plain, record, nil
}

func hashAPIKey(raw string) string {
	sum := sha256.Sum256([]byte(raw))
	return hex.EncodeToString(sum[:])
}

func extractAPIKeyPrefix(raw string) (string, bool) {
	parts := strings.Split(raw, "_")
	if len(parts) != 3 {
		return "", false
	}
	if parts[0] != "day1" || strings.TrimSpace(parts[1]) == "" || strings.TrimSpace(parts[2]) == "" {
		return "", false
	}
	return parts[1], true
}

func (s *Server) handleMemoryWrite(c *gin.Context) {
	var req kernel.WriteRequest
	if err := c.ShouldBindJSON(&req); err != nil {
		writeError(c, fmt.Errorf("%w: %v", kernel.ErrInvalidInput, err))
		return
	}
	memory, err := s.kernel.Write(c.Request.Context(), req)
	if err != nil {
		writeError(c, err)
		return
	}
	if err := s.bumpSessionMemory(s.currentUserID(c), req.SessionID, memory.BranchName, 1); err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, memory)
}

func (s *Server) handleMemoryTimeline(c *gin.Context) {
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "20"))
	items, err := s.kernel.Timeline(c.Request.Context(), kernel.TimelineRequest{
		BranchName: c.DefaultQuery("branch", "main"),
		Category:   c.Query("category"),
		SourceType: c.Query("source_type"),
		SessionID:  c.Query("session_id"),
		Limit:      limit,
	})
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"timeline": items, "count": len(items)})
}

func (s *Server) handleMemoryCount(c *gin.Context) {
	branch := c.DefaultQuery("branch", "main")
	count, err := s.kernel.Count(c.Request.Context(), branch, false)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"branch": branch, "count": count})
}

func (s *Server) handleMemoryGet(c *gin.Context) {
	memory, err := s.kernel.Get(c.Request.Context(), c.Param("memory_id"))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, memory)
}

func (s *Server) handleMemoryUpdate(c *gin.Context) {
	var payload struct {
		Text        *string        `json:"text"`
		Context     *string        `json:"context"`
		FileContext *string        `json:"file_context"`
		Category    *string        `json:"category"`
		SourceType  *string        `json:"source_type"`
		Status      *string        `json:"status"`
		Confidence  *float64       `json:"confidence"`
		Metadata    map[string]any `json:"metadata"`
	}
	if err := c.ShouldBindJSON(&payload); err != nil {
		writeError(c, fmt.Errorf("%w: %v", kernel.ErrInvalidInput, err))
		return
	}
	memory, err := s.kernel.Update(c.Request.Context(), kernel.UpdateRequest{
		MemoryID:    c.Param("memory_id"),
		Text:        payload.Text,
		Context:     payload.Context,
		FileContext: payload.FileContext,
		Category:    payload.Category,
		SourceType:  payload.SourceType,
		Status:      payload.Status,
		Confidence:  payload.Confidence,
		Metadata:    payload.Metadata,
	})
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, memory)
}

func (s *Server) handleMemoryArchive(c *gin.Context) {
	memory, err := s.kernel.Archive(c.Request.Context(), c.Param("memory_id"))
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, memory)
}

func (s *Server) handleMemoryBatchWrite(c *gin.Context) {
	var payload struct {
		Items  []kernel.WriteRequest `json:"items"`
		Branch string                `json:"branch"`
	}
	if err := c.ShouldBindJSON(&payload); err != nil {
		writeError(c, fmt.Errorf("%w: %v", kernel.ErrInvalidInput, err))
		return
	}
	if payload.Branch != "" {
		for i := range payload.Items {
			if payload.Items[i].BranchName == "" {
				payload.Items[i].BranchName = payload.Branch
			}
		}
	}
	items, err := s.kernel.WriteBatch(c.Request.Context(), payload.Items)
	if err != nil {
		writeError(c, err)
		return
	}
	sessionWrites := make(map[string]int)
	sessionBranch := make(map[string]string)
	for _, item := range items {
		if item.SessionID == "" {
			continue
		}
		sessionWrites[item.SessionID]++
		sessionBranch[item.SessionID] = item.BranchName
	}
	userID := s.currentUserID(c)
	for sessionID, count := range sessionWrites {
		if err := s.bumpSessionMemory(userID, sessionID, sessionBranch[sessionID], count); err != nil {
			writeError(c, err)
			return
		}
	}
	c.JSON(http.StatusOK, gin.H{"items": items, "count": len(items)})
}

func (s *Server) handleMemoryBatchArchive(c *gin.Context) {
	var payload struct {
		MemoryIDs []string `json:"memory_ids"`
	}
	if err := c.ShouldBindJSON(&payload); err != nil {
		writeError(c, fmt.Errorf("%w: %v", kernel.ErrInvalidInput, err))
		return
	}
	count, err := s.kernel.ArchiveBatch(c.Request.Context(), payload.MemoryIDs)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"archived": count})
}

func (s *Server) handleRelationCreate(c *gin.Context) {
	var payload struct {
		TargetID     string         `json:"target_id"`
		RelationType string         `json:"relation_type"`
		Weight       float64        `json:"weight"`
		Metadata     map[string]any `json:"metadata"`
	}
	if err := c.ShouldBindJSON(&payload); err != nil {
		writeError(c, fmt.Errorf("%w: %v", kernel.ErrInvalidInput, err))
		return
	}
	relation, err := s.kernel.Relate(
		c.Request.Context(),
		c.Param("memory_id"),
		payload.TargetID,
		payload.RelationType,
		payload.Weight,
		payload.Metadata,
	)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, relation)
}

func (s *Server) handleRelationList(c *gin.Context) {
	rels, err := s.kernel.Relations(
		c.Request.Context(),
		c.Param("memory_id"),
		c.Query("relation_type"),
		c.DefaultQuery("direction", "both"),
	)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"relations": rels, "count": len(rels)})
}

func (s *Server) handleMemoryGraph(c *gin.Context) {
	depth, _ := strconv.Atoi(c.DefaultQuery("depth", "1"))
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "50"))
	graph, err := s.kernel.Graph(c.Request.Context(), c.Param("memory_id"), depth, limit)
	if err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, graph)
}

func (s *Server) handleRelationDelete(c *gin.Context) {
	if err := s.kernel.DeleteRelation(c.Request.Context(), c.Param("relation_id")); err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"deleted": true})
}

func (s *Server) handleMCPTools(c *gin.Context) {
	tools := s.registry.ListTools()
	c.JSON(http.StatusOK, gin.H{"count": len(tools), "tools": tools})
}

func (s *Server) handleMCPInvoke(c *gin.Context) {
	var payload struct {
		Tool      string         `json:"tool"`
		Arguments map[string]any `json:"arguments"`
		SessionID string         `json:"session_id"`
	}
	if err := c.ShouldBindJSON(&payload); err != nil {
		writeError(c, fmt.Errorf("%w: %v", kernel.ErrInvalidInput, err))
		return
	}
	if payload.Arguments == nil {
		payload.Arguments = map[string]any{}
	}
	if payload.SessionID != "" {
		if _, exists := payload.Arguments["session_id"]; !exists {
			payload.Arguments["session_id"] = payload.SessionID
		}
	}
	result, err := s.registry.CallTool(c.Request.Context(), payload.Tool, payload.Arguments)
	if err != nil {
		if strings.Contains(err.Error(), "unknown tool") {
			c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
			return
		}
		writeError(c, err)
		return
	}
	if err := s.processMCPToolSideEffects(c.Request.Context(), payload.Tool, payload.Arguments, result); err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"tool": payload.Tool, "session_id": payload.SessionID, "result": result})
}

func (s *Server) handleMCPInvokePath(c *gin.Context) {
	var payload struct {
		Arguments map[string]any `json:"arguments"`
		SessionID string         `json:"session_id"`
	}
	if err := c.ShouldBindJSON(&payload); err != nil {
		writeError(c, fmt.Errorf("%w: %v", kernel.ErrInvalidInput, err))
		return
	}
	if payload.Arguments == nil {
		payload.Arguments = map[string]any{}
	}
	if payload.SessionID != "" {
		if _, exists := payload.Arguments["session_id"]; !exists {
			payload.Arguments["session_id"] = payload.SessionID
		}
	}
	toolName := c.Param("tool_name")
	result, err := s.registry.CallTool(c.Request.Context(), toolName, payload.Arguments)
	if err != nil {
		if strings.Contains(err.Error(), "unknown tool") {
			c.JSON(http.StatusNotFound, gin.H{"error": err.Error()})
			return
		}
		writeError(c, err)
		return
	}
	if err := s.processMCPToolSideEffects(c.Request.Context(), toolName, payload.Arguments, result); err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"tool": toolName, "session_id": payload.SessionID, "result": result})
}

func (s *Server) processMCPToolSideEffects(ctx context.Context, tool string, args map[string]any, result any) error {
	userID := kernel.UserIDFromContext(ctx)
	switch tool {
	case "memory_write":
		sessionID := getMapString(args, "session_id", "")
		branch := getMapString(args, "branch", getMapString(args, "branch_name", "main"))
		if mem, ok := result.(kernel.Memory); ok {
			if sessionID == "" {
				sessionID = mem.SessionID
			}
			if branch == "" {
				branch = mem.BranchName
			}
		}
		return s.bumpSessionMemory(userID, sessionID, branch, 1)
	case "memory_write_batch":
		rawItems := getMapSlice(args, "items")
		counts := map[string]int{}
		branches := map[string]string{}
		for _, raw := range rawItems {
			item, ok := raw.(map[string]any)
			if !ok {
				continue
			}
			sid := getMapString(item, "session_id", "")
			if sid == "" {
				continue
			}
			counts[sid]++
			branches[sid] = getMapString(item, "branch", getMapString(args, "branch", "main"))
		}
		for sid, count := range counts {
			if err := s.bumpSessionMemory(userID, sid, branches[sid], count); err != nil {
				return err
			}
		}
	}
	return nil
}

func (s *Server) handleClaudeHook(c *gin.Context) {
	event := c.GetHeader("X-Day1-Hook-Event")
	if event == "" {
		event = "unknown"
	}
	var body map[string]any
	if err := c.ShouldBindJSON(&body); err != nil {
		writeError(c, fmt.Errorf("%w: invalid hook payload", kernel.ErrInvalidInput))
		return
	}
	sessionID := getAnyString(body, "session_id")
	if sessionID == "" {
		sessionID = strings.TrimSpace(c.GetHeader("X-Day1-Session-Id"))
	}
	userID := s.currentUserID(c)
	entry := map[string]any{
		"event":      event,
		"user_id":    userID,
		"session_id": sessionID,
		"payload":    body,
		"created_at": time.Now().UTC(),
	}
	if _, err := s.appendHook(c.Request.Context(), entry); err != nil {
		writeError(c, err)
		return
	}
	if err := s.bumpSessionHook(userID, sessionID, getAnyString(body, "branch"), 1); err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"status": "ok", "event": event, "session_id": sessionID})
}

func (s *Server) handleRawHook(c *gin.Context) {
	event := c.GetHeader("X-Day1-Hook-Event")
	var body map[string]any
	if err := c.ShouldBindJSON(&body); err != nil {
		writeError(c, fmt.Errorf("%w: invalid hook payload", kernel.ErrInvalidInput))
		return
	}
	if event == "" {
		event = anyToString(body["event"])
	}
	if event == "" {
		event = getAnyStringFromContext(c, "event", "unknown")
	}
	sessionID := getAnyString(body, "session_id")
	if sessionID == "" {
		sessionID = strings.TrimSpace(c.GetHeader("X-Day1-Session-Id"))
	}
	userID := s.currentUserID(c)
	entry := map[string]any{
		"event":      event,
		"user_id":    userID,
		"session_id": sessionID,
		"payload":    body,
		"created_at": time.Now().UTC(),
	}
	stored, err := s.appendHook(c.Request.Context(), entry)
	if err != nil {
		writeError(c, err)
		return
	}
	if err := s.bumpSessionHook(userID, sessionID, getAnyString(body, "branch"), 1); err != nil {
		writeError(c, err)
		return
	}
	seq, _ := stored["seq"].(int64)
	if seq == 0 {
		if floatSeq, ok := stored["seq"].(float64); ok {
			seq = int64(floatSeq)
		}
	}
	c.JSON(http.StatusOK, gin.H{"seq": seq, "event": event, "memory_id": nil})
}

func (s *Server) handleListHooks(c *gin.Context) {
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "50"))
	offset, _ := strconv.Atoi(c.DefaultQuery("offset", "0"))
	event := c.Query("event")
	sessionID := c.Query("session_id")
	if limit <= 0 {
		limit = 50
	}
	if offset < 0 {
		offset = 0
	}

	s.hooksMu.RLock()
	filtered := make([]map[string]any, 0, len(s.hooks))
	userID := s.currentUserID(c)
	for i := len(s.hooks) - 1; i >= 0; i-- {
		entry := s.hooks[i]
		if userID != "" && getAnyString(entry, "user_id") != userID {
			continue
		}
		if event != "" && entry["event"] != event {
			continue
		}
		if sessionID != "" && entry["session_id"] != sessionID {
			continue
		}
		filtered = append(filtered, entry)
	}
	s.hooksMu.RUnlock()

	if offset > len(filtered) {
		offset = len(filtered)
	}
	end := offset + limit
	if end > len(filtered) {
		end = len(filtered)
	}

	items := []map[string]any{}
	if offset <= end && offset < len(filtered) {
		items = filtered[offset:end]
	}
	c.JSON(http.StatusOK, gin.H{"logs": items, "count": len(filtered)})
}

func (s *Server) handleSessionsList(c *gin.Context) {
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "50"))
	if limit <= 0 {
		limit = 50
	}
	branch := c.Query("branch")
	status := c.Query("status")
	userID := s.currentUserID(c)

	s.metaMu.RLock()
	items := make([]sessionState, 0, len(s.sessions))
	for _, session := range s.sessions {
		if userID != "" && session.UserID != userID {
			continue
		}
		if branch != "" && session.BranchName != branch {
			continue
		}
		if status != "" && session.Status != status {
			continue
		}
		items = append(items, *session)
	}
	s.metaMu.RUnlock()

	sort.Slice(items, func(i, j int) bool {
		return items[i].StartedAt.After(items[j].StartedAt)
	})
	if len(items) > limit {
		items = items[:limit]
	}
	c.JSON(http.StatusOK, gin.H{"sessions": items, "count": len(items)})
}

func (s *Server) handleSessionGet(c *gin.Context) {
	sessionID := c.Param("session_id")
	userID := s.currentUserID(c)
	s.metaMu.RLock()
	session, ok := s.sessions[sessionKey(userID, sessionID)]
	if !ok {
		s.metaMu.RUnlock()
		c.JSON(http.StatusNotFound, gin.H{"error": "session not found"})
		return
	}
	snapshot := *session
	traces := make([]traceState, 0)
	for _, trace := range s.traces {
		if userID != "" && trace.UserID != userID {
			continue
		}
		if trace.SessionID == sessionID {
			traces = append(traces, trace)
		}
	}
	s.metaMu.RUnlock()

	sort.Slice(traces, func(i, j int) bool {
		return traces[i].CreatedAt.After(traces[j].CreatedAt)
	})

	memories, err := s.kernel.Timeline(c.Request.Context(), kernel.TimelineRequest{
		BranchName: snapshot.BranchName,
		SessionID:  sessionID,
		Limit:      1000,
	})
	if err != nil {
		writeError(c, err)
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"session":    snapshot,
		"memories":   memories,
		"traces":     traces,
		"hook_count": snapshot.HookCount,
	})
}

func (s *Server) handleSessionSummary(c *gin.Context) {
	sessionID := c.Param("session_id")
	userID := s.currentUserID(c)
	s.metaMu.RLock()
	session, ok := s.sessions[sessionKey(userID, sessionID)]
	s.metaMu.RUnlock()
	if !ok {
		c.JSON(http.StatusNotFound, gin.H{"error": "session not found"})
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"session_id":   session.ID,
		"branch":       session.BranchName,
		"status":       session.Status,
		"memory_count": session.MemoryCount,
		"trace_count":  session.TraceCount,
		"hook_count":   session.HookCount,
	})
}

func (s *Server) handleSessionCheckpoint(c *gin.Context) {
	sessionID := c.Param("session_id")
	var body struct {
		Category   string  `json:"category"`
		Text       string  `json:"text"`
		Context    string  `json:"context"`
		TraceID    string  `json:"trace_id"`
		Branch     string  `json:"branch"`
		Confidence float64 `json:"confidence"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		writeError(c, fmt.Errorf("%w: %v", kernel.ErrInvalidInput, err))
		return
	}
	if strings.TrimSpace(body.Category) == "" || strings.TrimSpace(body.Text) == "" {
		writeError(c, fmt.Errorf("%w: category and text are required", kernel.ErrInvalidInput))
		return
	}
	if body.Confidence == 0 {
		body.Confidence = 0.85
	}

	memory, err := s.kernel.Write(c.Request.Context(), kernel.WriteRequest{
		Text:       body.Text,
		Context:    body.Context,
		SessionID:  sessionID,
		TraceID:    body.TraceID,
		Category:   body.Category,
		SourceType: "trace_checkpoint",
		BranchName: body.Branch,
		Confidence: body.Confidence,
	})
	if err != nil {
		writeError(c, err)
		return
	}
	if err := s.bumpSessionMemory(s.currentUserID(c), sessionID, memory.BranchName, 1); err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{
		"session_id": sessionID,
		"category":   body.Category,
		"memory_id":  memory.ID,
		"result":     memory,
	})
}

func (s *Server) handleTraceList(c *gin.Context) {
	limit, _ := strconv.Atoi(c.DefaultQuery("limit", "50"))
	offset, _ := strconv.Atoi(c.DefaultQuery("offset", "0"))
	if limit <= 0 {
		limit = 50
	}
	if offset < 0 {
		offset = 0
	}

	sessionID := c.Query("session_id")
	branch := c.Query("branch")
	traceType := c.Query("trace_type")
	skillID := c.Query("skill_id")
	userID := s.currentUserID(c)

	s.metaMu.RLock()
	filtered := make([]traceState, 0, len(s.traces))
	for _, trace := range s.traces {
		if userID != "" && trace.UserID != userID {
			continue
		}
		if sessionID != "" && trace.SessionID != sessionID {
			continue
		}
		if branch != "" && trace.Branch != branch {
			continue
		}
		if traceType != "" && trace.TraceType != traceType {
			continue
		}
		if skillID != "" && trace.SkillID != skillID {
			continue
		}
		filtered = append(filtered, trace)
	}
	s.metaMu.RUnlock()

	sort.Slice(filtered, func(i, j int) bool {
		return filtered[i].CreatedAt.After(filtered[j].CreatedAt)
	})

	total := len(filtered)
	if offset > total {
		offset = total
	}
	end := offset + limit
	if end > total {
		end = total
	}
	if offset < end {
		filtered = filtered[offset:end]
	} else {
		filtered = []traceState{}
	}
	c.JSON(http.StatusOK, gin.H{"traces": filtered, "count": total})
}

func (s *Server) handleTraceGet(c *gin.Context) {
	traceID := c.Param("trace_id")
	userID := s.currentUserID(c)
	s.metaMu.RLock()
	trace, ok := s.traces[traceID]
	s.metaMu.RUnlock()
	if !ok || (userID != "" && trace.UserID != userID) {
		c.JSON(http.StatusNotFound, gin.H{"error": "trace not found"})
		return
	}
	c.JSON(http.StatusOK, trace)
}

func (s *Server) handleTraceCreate(c *gin.Context) {
	var body struct {
		Steps           []map[string]any `json:"steps"`
		TraceType       string           `json:"trace_type"`
		ParentTraceID   string           `json:"parent_trace_id"`
		SkillID         string           `json:"skill_id"`
		SessionID       string           `json:"session_id"`
		Branch          string           `json:"branch"`
		TaskDescription string           `json:"task_description"`
		Metadata        map[string]any   `json:"metadata"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		writeError(c, fmt.Errorf("%w: %v", kernel.ErrInvalidInput, err))
		return
	}
	if len(body.Steps) == 0 {
		writeError(c, fmt.Errorf("%w: steps are required", kernel.ErrInvalidInput))
		return
	}

	trace := traceState{
		ID:              uuid.NewString(),
		UserID:          s.currentUserID(c),
		SessionID:       body.SessionID,
		Branch:          defaultString(body.Branch, "main"),
		TraceType:       defaultString(body.TraceType, "replay"),
		ParentTraceID:   body.ParentTraceID,
		SkillID:         body.SkillID,
		TaskDescription: body.TaskDescription,
		Steps:           body.Steps,
		Metadata:        body.Metadata,
		CreatedAt:       time.Now().UTC(),
	}
	if err := s.persistTrace(c.Request.Context(), trace); err != nil {
		writeError(c, err)
		return
	}
	s.metaMu.Lock()
	s.traces[trace.ID] = trace
	s.metaMu.Unlock()
	if err := s.bumpSessionTrace(s.currentUserID(c), trace.SessionID, trace.Branch, 1); err != nil {
		writeError(c, err)
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"id":               trace.ID,
		"session_id":       trace.SessionID,
		"branch":           trace.Branch,
		"trace_type":       trace.TraceType,
		"parent_trace_id":  trace.ParentTraceID,
		"skill_id":         trace.SkillID,
		"task_description": trace.TaskDescription,
		"steps":            trace.Steps,
		"metadata":         trace.Metadata,
		"created_at":       trace.CreatedAt,
		"artifacts": gin.H{
			"learning": gin.H{"step_count": len(trace.Steps), "trace_type": trace.TraceType},
			"handoff":  gin.H{"session_id": trace.SessionID, "branch": trace.Branch},
		},
		"checkpoint_report": gin.H{"captured": []any{}, "errors": []any{}},
	})
}

func (s *Server) handleTraceExtract(c *gin.Context) {
	var body struct {
		SessionID       string `json:"session_id"`
		Branch          string `json:"branch"`
		TaskDescription string `json:"task_description"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		writeError(c, fmt.Errorf("%w: %v", kernel.ErrInvalidInput, err))
		return
	}
	if strings.TrimSpace(body.SessionID) == "" {
		writeError(c, fmt.Errorf("%w: session_id is required", kernel.ErrInvalidInput))
		return
	}

	steps := make([]map[string]any, 0)
	s.hooksMu.RLock()
	userID := s.currentUserID(c)
	for idx, entry := range s.hooks {
		if userID != "" && getAnyString(entry, "user_id") != userID {
			continue
		}
		if getAnyString(entry, "session_id") != body.SessionID {
			continue
		}
		steps = append(steps, map[string]any{
			"index":   idx + 1,
			"event":   entry["event"],
			"payload": entry["payload"],
		})
	}
	s.hooksMu.RUnlock()
	if len(steps) == 0 {
		steps = append(steps, map[string]any{"index": 1, "event": "empty_extract", "payload": map[string]any{}})
	}

	trace := traceState{
		ID:              uuid.NewString(),
		UserID:          s.currentUserID(c),
		SessionID:       body.SessionID,
		Branch:          defaultString(body.Branch, "main"),
		TraceType:       "original",
		TaskDescription: body.TaskDescription,
		Steps:           steps,
		CreatedAt:       time.Now().UTC(),
	}
	if err := s.persistTrace(c.Request.Context(), trace); err != nil {
		writeError(c, err)
		return
	}
	s.metaMu.Lock()
	s.traces[trace.ID] = trace
	s.metaMu.Unlock()
	if err := s.bumpSessionTrace(s.currentUserID(c), trace.SessionID, trace.Branch, 1); err != nil {
		writeError(c, err)
		return
	}

	c.JSON(http.StatusOK, gin.H{
		"id":               trace.ID,
		"session_id":       trace.SessionID,
		"branch":           trace.Branch,
		"trace_type":       trace.TraceType,
		"task_description": trace.TaskDescription,
		"steps":            trace.Steps,
		"created_at":       trace.CreatedAt,
		"artifacts": gin.H{
			"learning": gin.H{"step_count": len(trace.Steps), "source": "hook_logs"},
			"handoff":  gin.H{"session_id": trace.SessionID, "branch": trace.Branch},
		},
		"checkpoint_report": gin.H{"captured": []any{}, "errors": []any{}},
	})
}

func (s *Server) handleTraceCompare(c *gin.Context) {
	traceAID := c.Param("trace_a_id")
	traceBID := c.Param("trace_b_id")

	var body struct {
		Dimensions []string `json:"dimensions"`
		SkillID    string   `json:"skill_id"`
	}
	if err := c.ShouldBindJSON(&body); err != nil {
		body = struct {
			Dimensions []string `json:"dimensions"`
			SkillID    string   `json:"skill_id"`
		}{}
	}

	s.metaMu.RLock()
	userID := s.currentUserID(c)
	traceA, okA := s.traces[traceAID]
	traceB, okB := s.traces[traceBID]
	s.metaMu.RUnlock()
	if !okA || !okB || (userID != "" && (traceA.UserID != userID || traceB.UserID != userID)) {
		c.JSON(http.StatusNotFound, gin.H{"error": "trace not found"})
		return
	}

	scores := buildDimensionScores(traceA, traceB)
	if len(body.Dimensions) > 0 {
		filtered := map[string]float64{}
		for _, dim := range body.Dimensions {
			if score, ok := scores[dim]; ok {
				filtered[dim] = score
			}
		}
		if len(filtered) > 0 {
			scores = filtered
		}
	}
	avg := 0.0
	for _, score := range scores {
		avg += score
	}
	avg /= math.Max(float64(len(scores)), 1)
	verdict := "different"
	if avg >= 0.80 {
		verdict = "similar"
	} else if avg >= 0.60 {
		verdict = "related"
	}

	comparison := comparisonState{
		ID:              uuid.NewString(),
		UserID:          userID,
		TraceAID:        traceAID,
		TraceBID:        traceBID,
		SkillID:         body.SkillID,
		DimensionScores: scores,
		Verdict:         verdict,
		Insights: map[string]any{
			"average_score": avg,
			"a_steps":       len(traceA.Steps),
			"b_steps":       len(traceB.Steps),
		},
		CreatedAt: time.Now().UTC(),
	}
	if err := s.persistComparison(c.Request.Context(), comparison); err != nil {
		writeError(c, err)
		return
	}

	s.metaMu.Lock()
	s.comparisons = append(s.comparisons, comparison)
	s.metaMu.Unlock()

	c.JSON(http.StatusOK, comparison)
}

func buildDimensionScores(traceA, traceB traceState) map[string]float64 {
	maxSteps := math.Max(float64(len(traceA.Steps)), float64(len(traceB.Steps)))
	stepSimilarity := 1.0
	if maxSteps > 0 {
		stepSimilarity = 1.0 - (math.Abs(float64(len(traceA.Steps)-len(traceB.Steps))) / maxSteps)
	}
	branchAlignment := 0.0
	if traceA.Branch == traceB.Branch {
		branchAlignment = 1.0
	}
	sessionAlignment := 0.0
	if traceA.SessionID != "" && traceA.SessionID == traceB.SessionID {
		sessionAlignment = 1.0
	} else if traceA.SessionID == "" || traceB.SessionID == "" {
		sessionAlignment = 0.5
	}
	return map[string]float64{
		"step_similarity":    clampScore(stepSimilarity),
		"branch_alignment":   clampScore(branchAlignment),
		"session_alignment":  clampScore(sessionAlignment),
		"trace_type_overlap": clampScore(boolToScore(traceA.TraceType == traceB.TraceType)),
	}
}

func clampScore(v float64) float64 {
	if v < 0 {
		return 0
	}
	if v > 1 {
		return 1
	}
	return v
}

func boolToScore(v bool) float64 {
	if v {
		return 1
	}
	return 0
}

func (s *Server) appendHook(ctx context.Context, entry map[string]any) (map[string]any, error) {
	if entry["created_at"] == nil {
		entry["created_at"] = time.Now().UTC()
	}
	if s.meta != nil {
		hook := meta.HookLog{
			Event:     getAnyString(entry, "event"),
			UserID:    getAnyString(entry, "user_id"),
			SessionID: getAnyString(entry, "session_id"),
			Payload:   getAnyMap(entry, "payload"),
			CreatedAt: toTime(entry["created_at"]),
		}
		seq, err := s.meta.InsertHookLog(ctx, hook)
		if err != nil {
			return nil, err
		}
		entry["seq"] = seq
	}

	s.hooksMu.Lock()
	if entry["seq"] == nil {
		entry["seq"] = int64(len(s.hooks) + 1)
	}
	s.hooks = append(s.hooks, entry)
	s.hooksMu.Unlock()
	return entry, nil
}

func (s *Server) bumpSessionMemory(userID, sessionID, branch string, delta int) error {
	if strings.TrimSpace(sessionID) == "" || delta <= 0 {
		return nil
	}
	s.metaMu.Lock()
	session := s.ensureSessionLocked(userID, sessionID, branch)
	session.MemoryCount += delta
	err := s.persistSessionLocked(context.Background(), session)
	s.metaMu.Unlock()
	return err
}

func (s *Server) bumpSessionTrace(userID, sessionID, branch string, delta int) error {
	if strings.TrimSpace(sessionID) == "" || delta <= 0 {
		return nil
	}
	s.metaMu.Lock()
	session := s.ensureSessionLocked(userID, sessionID, branch)
	session.TraceCount += delta
	err := s.persistSessionLocked(context.Background(), session)
	s.metaMu.Unlock()
	return err
}

func (s *Server) bumpSessionHook(userID, sessionID, branch string, delta int) error {
	if strings.TrimSpace(sessionID) == "" || delta <= 0 {
		return nil
	}
	s.metaMu.Lock()
	session := s.ensureSessionLocked(userID, sessionID, branch)
	session.HookCount += delta
	err := s.persistSessionLocked(context.Background(), session)
	s.metaMu.Unlock()
	return err
}

func (s *Server) ensureSessionLocked(userID, sessionID, branch string) *sessionState {
	if branch == "" {
		branch = "main"
	}
	key := sessionKey(userID, sessionID)
	if existing, ok := s.sessions[key]; ok {
		if existing.BranchName == "" {
			existing.BranchName = branch
		}
		if existing.Status == "" {
			existing.Status = "active"
		}
		if existing.StartedAt.IsZero() {
			existing.StartedAt = time.Now().UTC()
		}
		return existing
	}
	now := time.Now().UTC()
	created := &sessionState{
		ID:         sessionID,
		UserID:     userID,
		BranchName: branch,
		Status:     "active",
		StartedAt:  now,
	}
	s.sessions[key] = created
	return created
}

func (s *Server) persistSessionLocked(ctx context.Context, session *sessionState) error {
	if s.meta == nil || session == nil {
		return nil
	}
	return s.meta.UpsertSession(ctx, meta.Session{
		ID:          session.ID,
		UserID:      session.UserID,
		BranchName:  session.BranchName,
		Status:      session.Status,
		StartedAt:   session.StartedAt,
		EndedAt:     session.EndedAt,
		MemoryCount: session.MemoryCount,
		TraceCount:  session.TraceCount,
		HookCount:   session.HookCount,
	})
}

func (s *Server) persistTrace(ctx context.Context, trace traceState) error {
	if s.meta == nil {
		return nil
	}
	return s.meta.UpsertTrace(ctx, meta.Trace{
		ID:              trace.ID,
		UserID:          trace.UserID,
		SessionID:       trace.SessionID,
		BranchName:      trace.Branch,
		TraceType:       trace.TraceType,
		ParentTraceID:   trace.ParentTraceID,
		SkillID:         trace.SkillID,
		TaskDescription: trace.TaskDescription,
		Steps:           trace.Steps,
		Metadata:        trace.Metadata,
		CreatedAt:       trace.CreatedAt,
	})
}

func (s *Server) persistComparison(ctx context.Context, comparison comparisonState) error {
	if s.meta == nil {
		return nil
	}
	return s.meta.UpsertComparison(ctx, meta.Comparison{
		ID:              comparison.ID,
		UserID:          comparison.UserID,
		TraceAID:        comparison.TraceAID,
		TraceBID:        comparison.TraceBID,
		SkillID:         comparison.SkillID,
		DimensionScores: comparison.DimensionScores,
		Verdict:         comparison.Verdict,
		Insights:        comparison.Insights,
		CreatedAt:       comparison.CreatedAt,
	})
}

func writeError(c *gin.Context, err error) {
	status := http.StatusInternalServerError
	msg := err.Error()
	if errors.Is(err, kernel.ErrInvalidInput) {
		status = http.StatusBadRequest
	} else if errors.Is(err, kernel.ErrMemoryNotFound) || errors.Is(err, kernel.ErrBranchNotFound) || errors.Is(err, kernel.ErrSnapshotNotFound) || errors.Is(err, kernel.ErrRelationNotFound) {
		status = http.StatusNotFound
	} else if errors.Is(err, kernel.ErrBranchExists) || errors.Is(err, kernel.ErrInvalidBranch) {
		status = http.StatusConflict
	}
	c.JSON(status, gin.H{"error": msg})
}

func getAnyString(data map[string]any, key string) string {
	v, ok := data[key]
	if !ok || v == nil {
		return ""
	}
	s, ok := v.(string)
	if !ok {
		return ""
	}
	return strings.TrimSpace(s)
}

func anyToString(v any) string {
	s, ok := v.(string)
	if !ok {
		return ""
	}
	return strings.TrimSpace(s)
}

func getAnyMap(data map[string]any, key string) map[string]any {
	v, ok := data[key]
	if !ok || v == nil {
		return map[string]any{}
	}
	m, ok := v.(map[string]any)
	if !ok {
		return map[string]any{}
	}
	return m
}

func toTime(v any) time.Time {
	t, ok := v.(time.Time)
	if ok {
		return t.UTC()
	}
	return time.Now().UTC()
}

func getAnyStringFromContext(c *gin.Context, key, fallback string) string {
	v := strings.TrimSpace(c.Query(key))
	if v == "" {
		return fallback
	}
	return v
}

func defaultString(v, fallback string) string {
	if strings.TrimSpace(v) == "" {
		return fallback
	}
	return v
}

func sessionKey(userID, sessionID string) string {
	return strings.TrimSpace(userID) + "::" + strings.TrimSpace(sessionID)
}

func getMapString(m map[string]any, key, fallback string) string {
	value, ok := m[key]
	if !ok || value == nil {
		return fallback
	}
	s, ok := value.(string)
	if !ok || strings.TrimSpace(s) == "" {
		return fallback
	}
	return strings.TrimSpace(s)
}

func getMapSlice(m map[string]any, key string) []any {
	value, ok := m[key]
	if !ok || value == nil {
		return nil
	}
	raw, ok := value.([]any)
	if ok {
		return raw
	}
	typed, ok := value.([]map[string]any)
	if ok {
		out := make([]any, 0, len(typed))
		for _, entry := range typed {
			out = append(out, entry)
		}
		return out
	}
	return nil
}

func SortedToolNames(tools []mcp.Tool) []string {
	names := make([]string, 0, len(tools))
	for _, t := range tools {
		names = append(names, t.Name)
	}
	sort.Strings(names)
	return names
}
