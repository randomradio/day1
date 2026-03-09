package api

import (
	"context"
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
}

type sessionState struct {
	ID          string     `json:"id"`
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

func NewServer(cfg config.Config, k kernel.MemoryKernel, registry *mcp.Registry, metadataStore MetadataStore) (*Server, error) {
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
		s.sessions[item.ID] = &sessionState{
			ID:          copy.ID,
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
	{
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
	if err := s.bumpSessionMemory(req.SessionID, memory.BranchName, 1); err != nil {
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
	for sessionID, count := range sessionWrites {
		if err := s.bumpSessionMemory(sessionID, sessionBranch[sessionID], count); err != nil {
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
	if err := s.processMCPToolSideEffects(payload.Tool, payload.Arguments, result); err != nil {
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
	if err := s.processMCPToolSideEffects(toolName, payload.Arguments, result); err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"tool": toolName, "session_id": payload.SessionID, "result": result})
}

func (s *Server) processMCPToolSideEffects(tool string, args map[string]any, result any) error {
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
		return s.bumpSessionMemory(sessionID, branch, 1)
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
			if err := s.bumpSessionMemory(sid, branches[sid], count); err != nil {
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
	entry := map[string]any{
		"event":      event,
		"session_id": sessionID,
		"payload":    body,
		"created_at": time.Now().UTC(),
	}
	if _, err := s.appendHook(c.Request.Context(), entry); err != nil {
		writeError(c, err)
		return
	}
	if err := s.bumpSessionHook(sessionID, getAnyString(body, "branch"), 1); err != nil {
		writeError(c, err)
		return
	}
	c.JSON(http.StatusOK, gin.H{"status": "ok", "event": event, "session_id": sessionID})
}

func (s *Server) handleRawHook(c *gin.Context) {
	event := c.GetHeader("X-Day1-Hook-Event")
	if event == "" {
		event = getAnyStringFromContext(c, "event", "unknown")
	}
	var body map[string]any
	if err := c.ShouldBindJSON(&body); err != nil {
		writeError(c, fmt.Errorf("%w: invalid hook payload", kernel.ErrInvalidInput))
		return
	}
	sessionID := getAnyString(body, "session_id")
	entry := map[string]any{
		"event":      event,
		"session_id": sessionID,
		"payload":    body,
		"created_at": time.Now().UTC(),
	}
	stored, err := s.appendHook(c.Request.Context(), entry)
	if err != nil {
		writeError(c, err)
		return
	}
	if err := s.bumpSessionHook(sessionID, getAnyString(body, "branch"), 1); err != nil {
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
	for i := len(s.hooks) - 1; i >= 0; i-- {
		entry := s.hooks[i]
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

	s.metaMu.RLock()
	items := make([]sessionState, 0, len(s.sessions))
	for _, session := range s.sessions {
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
	s.metaMu.RLock()
	session, ok := s.sessions[sessionID]
	if !ok {
		s.metaMu.RUnlock()
		c.JSON(http.StatusNotFound, gin.H{"error": "session not found"})
		return
	}
	snapshot := *session
	traces := make([]traceState, 0)
	for _, trace := range s.traces {
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
	s.metaMu.RLock()
	session, ok := s.sessions[sessionID]
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
	if err := s.bumpSessionMemory(sessionID, memory.BranchName, 1); err != nil {
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

	s.metaMu.RLock()
	filtered := make([]traceState, 0, len(s.traces))
	for _, trace := range s.traces {
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
	s.metaMu.RLock()
	trace, ok := s.traces[traceID]
	s.metaMu.RUnlock()
	if !ok {
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
	if err := s.bumpSessionTrace(trace.SessionID, trace.Branch, 1); err != nil {
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
	for idx, entry := range s.hooks {
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
	if err := s.bumpSessionTrace(trace.SessionID, trace.Branch, 1); err != nil {
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
	traceA, okA := s.traces[traceAID]
	traceB, okB := s.traces[traceBID]
	s.metaMu.RUnlock()
	if !okA || !okB {
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

func (s *Server) bumpSessionMemory(sessionID, branch string, delta int) error {
	if strings.TrimSpace(sessionID) == "" || delta <= 0 {
		return nil
	}
	s.metaMu.Lock()
	session := s.ensureSessionLocked(sessionID, branch)
	session.MemoryCount += delta
	err := s.persistSessionLocked(context.Background(), session)
	s.metaMu.Unlock()
	return err
}

func (s *Server) bumpSessionTrace(sessionID, branch string, delta int) error {
	if strings.TrimSpace(sessionID) == "" || delta <= 0 {
		return nil
	}
	s.metaMu.Lock()
	session := s.ensureSessionLocked(sessionID, branch)
	session.TraceCount += delta
	err := s.persistSessionLocked(context.Background(), session)
	s.metaMu.Unlock()
	return err
}

func (s *Server) bumpSessionHook(sessionID, branch string, delta int) error {
	if strings.TrimSpace(sessionID) == "" || delta <= 0 {
		return nil
	}
	s.metaMu.Lock()
	session := s.ensureSessionLocked(sessionID, branch)
	session.HookCount += delta
	err := s.persistSessionLocked(context.Background(), session)
	s.metaMu.Unlock()
	return err
}

func (s *Server) ensureSessionLocked(sessionID, branch string) *sessionState {
	if branch == "" {
		branch = "main"
	}
	if existing, ok := s.sessions[sessionID]; ok {
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
		BranchName: branch,
		Status:     "active",
		StartedAt:  now,
	}
	s.sessions[sessionID] = created
	return created
}

func (s *Server) persistSessionLocked(ctx context.Context, session *sessionState) error {
	if s.meta == nil || session == nil {
		return nil
	}
	return s.meta.UpsertSession(ctx, meta.Session{
		ID:          session.ID,
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
