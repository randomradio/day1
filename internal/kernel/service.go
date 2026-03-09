package kernel

import (
	"context"
	"fmt"
	"math"
	"sort"
	"strings"
	"sync"
	"time"

	"github.com/google/uuid"
)

// MemoryService is the default memory-kernel implementation.
// It keeps an in-memory working set and can optionally persist to a StateStore.
type MemoryService struct {
	mu        sync.RWMutex
	embedder  EmbeddingProvider
	llm       LLMProvider
	store     StateStore
	memories  map[string]Memory
	branches  map[string]Branch
	snapshots map[string]Snapshot
	relations map[string]Relation
}

func NewMemoryService(embedder EmbeddingProvider, llm LLMProvider) *MemoryService {
	return newMemoryService(embedder, llm, nil)
}

func NewMemoryServiceWithStore(ctx context.Context, embedder EmbeddingProvider, llm LLMProvider, store StateStore) (*MemoryService, error) {
	svc := newMemoryService(embedder, llm, store)
	if err := svc.loadFromStore(ctx); err != nil {
		return nil, err
	}
	return svc, nil
}

func newMemoryService(embedder EmbeddingProvider, llm LLMProvider, store StateStore) *MemoryService {
	now := time.Now().UTC()
	return &MemoryService{
		embedder: embedder,
		llm:      llm,
		store:    store,
		memories: make(map[string]Memory),
		branches: map[string]Branch{
			"main": {
				Name:        "main",
				Description: "Default memory branch",
				Status:      "active",
				CreatedAt:   now,
				UpdatedAt:   now,
			},
		},
		snapshots: make(map[string]Snapshot),
		relations: make(map[string]Relation),
	}
}

func (s *MemoryService) loadFromStore(ctx context.Context) error {
	if s.store == nil {
		return nil
	}
	if err := s.store.EnsureSchema(ctx); err != nil {
		return fmt.Errorf("ensure kernel schema: %w", err)
	}
	state, err := s.store.LoadState(ctx)
	if err != nil {
		return fmt.Errorf("load kernel state: %w", err)
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	s.memories = make(map[string]Memory, len(state.Memories))
	for _, m := range state.Memories {
		s.memories[m.ID] = cloneMemory(m)
	}
	s.branches = make(map[string]Branch, len(state.Branches)+1)
	for _, b := range state.Branches {
		s.branches[b.Name] = b
	}
	s.snapshots = make(map[string]Snapshot, len(state.Snapshots))
	for _, snap := range state.Snapshots {
		s.snapshots[snap.ID] = snap
	}
	s.relations = make(map[string]Relation, len(state.Relations))
	for _, rel := range state.Relations {
		s.relations[rel.ID] = rel
	}
	if _, ok := s.branches["main"]; !ok {
		now := time.Now().UTC()
		main := Branch{Name: "main", Description: "Default memory branch", Status: "active", CreatedAt: now, UpdatedAt: now}
		s.branches["main"] = main
		if err := s.store.UpsertBranch(ctx, main); err != nil {
			return fmt.Errorf("persist default main branch: %w", err)
		}
	}
	return nil
}

func (s *MemoryService) Write(ctx context.Context, req WriteRequest) (Memory, error) {
	if strings.TrimSpace(req.Text) == "" {
		return Memory{}, fmt.Errorf("%w: text is required", ErrInvalidInput)
	}
	branch := defaultBranch(req.BranchName)

	var embedding []float32
	if s.embedder != nil {
		if emb, err := s.embedder.Embed(ctx, req.Text); err == nil {
			embedding = emb
		}
	}

	now := time.Now().UTC()
	memory := Memory{
		ID:          uuid.NewString(),
		Text:        req.Text,
		Context:     req.Context,
		FileContext: req.FileContext,
		SessionID:   req.SessionID,
		TraceID:     req.TraceID,
		Category:    req.Category,
		SourceType:  req.SourceType,
		Status:      defaultStatus(req.Status),
		BranchName:  branch,
		Confidence:  req.Confidence,
		Embedding:   embedding,
		Metadata:    cloneMap(req.Metadata),
		CreatedAt:   now,
		UpdatedAt:   now,
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.branches[branch]; !ok {
		return Memory{}, fmt.Errorf("%w: %s", ErrBranchNotFound, branch)
	}
	if err := s.persistMemory(ctx, memory); err != nil {
		return Memory{}, err
	}
	s.memories[memory.ID] = memory
	return cloneMemory(memory), nil
}

func (s *MemoryService) WriteBatch(ctx context.Context, reqs []WriteRequest) ([]Memory, error) {
	if len(reqs) == 0 {
		return []Memory{}, nil
	}

	texts := make([]string, 0, len(reqs))
	for _, req := range reqs {
		texts = append(texts, req.Text)
	}

	var embeddings [][]float32
	if s.embedder != nil {
		if emb, err := s.embedder.EmbedBatch(ctx, texts); err == nil && len(emb) == len(reqs) {
			embeddings = emb
		}
	}

	results := make([]Memory, 0, len(reqs))
	for i, req := range reqs {
		memory, err := s.Write(ctx, req)
		if err != nil {
			return nil, err
		}
		if len(embeddings) > 0 {
			s.mu.Lock()
			updated := s.memories[memory.ID]
			updated.Embedding = embeddings[i]
			if err := s.persistMemory(ctx, updated); err == nil {
				s.memories[memory.ID] = updated
				memory = cloneMemory(updated)
			}
			s.mu.Unlock()
		}
		results = append(results, memory)
	}
	return results, nil
}

func (s *MemoryService) Get(_ context.Context, memoryID string) (Memory, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	memory, ok := s.memories[memoryID]
	if !ok {
		return Memory{}, fmt.Errorf("%w: %s", ErrMemoryNotFound, memoryID)
	}
	return cloneMemory(memory), nil
}

func (s *MemoryService) Update(ctx context.Context, req UpdateRequest) (Memory, error) {
	s.mu.Lock()
	memory, ok := s.memories[req.MemoryID]
	if !ok {
		s.mu.Unlock()
		return Memory{}, fmt.Errorf("%w: %s", ErrMemoryNotFound, req.MemoryID)
	}

	textChanged := false
	updated := cloneMemory(memory)
	if req.Text != nil {
		if strings.TrimSpace(*req.Text) == "" {
			s.mu.Unlock()
			return Memory{}, fmt.Errorf("%w: text cannot be empty", ErrInvalidInput)
		}
		updated.Text = *req.Text
		textChanged = true
	}
	if req.Context != nil {
		updated.Context = *req.Context
	}
	if req.FileContext != nil {
		updated.FileContext = *req.FileContext
	}
	if req.Category != nil {
		updated.Category = *req.Category
	}
	if req.SourceType != nil {
		updated.SourceType = *req.SourceType
	}
	if req.Status != nil {
		updated.Status = *req.Status
	}
	if req.Confidence != nil {
		updated.Confidence = *req.Confidence
	}
	if req.Metadata != nil {
		updated.Metadata = cloneMap(req.Metadata)
	}
	updated.UpdatedAt = time.Now().UTC()

	if err := s.persistMemory(ctx, updated); err != nil {
		s.mu.Unlock()
		return Memory{}, err
	}
	s.memories[req.MemoryID] = updated
	s.mu.Unlock()

	if textChanged && s.embedder != nil {
		if emb, err := s.embedder.Embed(ctx, updated.Text); err == nil {
			s.mu.Lock()
			postEmbed := s.memories[req.MemoryID]
			postEmbed.Embedding = emb
			if err := s.persistMemory(ctx, postEmbed); err == nil {
				s.memories[req.MemoryID] = postEmbed
				updated = postEmbed
			}
			s.mu.Unlock()
		}
	}

	return cloneMemory(updated), nil
}

func (s *MemoryService) Archive(ctx context.Context, memoryID string) (Memory, error) {
	status := "archived"
	return s.Update(ctx, UpdateRequest{MemoryID: memoryID, Status: &status})
}

func (s *MemoryService) ArchiveBatch(ctx context.Context, memoryIDs []string) (int, error) {
	count := 0
	for _, id := range memoryIDs {
		m, err := s.Get(ctx, id)
		if err != nil {
			continue
		}
		if m.Status == "archived" {
			continue
		}
		if _, err := s.Archive(ctx, id); err == nil {
			count++
		}
	}
	return count, nil
}

func (s *MemoryService) Search(ctx context.Context, req SearchRequest) ([]SearchResult, error) {
	branch := defaultBranch(req.BranchName)
	limit := req.Limit
	if limit <= 0 {
		limit = 20
	}

	s.mu.RLock()
	candidates := make([]Memory, 0, len(s.memories))
	for _, m := range s.memories {
		if !matchMemoryFilter(m, branch, req.Category, req.SourceType, req.Status, req.SessionID, false) {
			continue
		}
		candidates = append(candidates, cloneMemory(m))
	}
	s.mu.RUnlock()

	query := strings.TrimSpace(req.Query)
	if query == "" {
		sort.Slice(candidates, func(i, j int) bool {
			return candidates[i].CreatedAt.After(candidates[j].CreatedAt)
		})
		return toSearchResults(candidates, limit), nil
	}

	var queryEmbedding []float32
	if s.embedder != nil {
		if emb, err := s.embedder.Embed(ctx, query); err == nil {
			queryEmbedding = emb
		}
	}

	results := make([]SearchResult, 0, len(candidates))
	q := strings.ToLower(query)
	for _, m := range candidates {
		score := 0.0
		if len(queryEmbedding) > 0 && len(m.Embedding) > 0 {
			score += cosineSimilarity(queryEmbedding, m.Embedding)
		}
		if strings.Contains(strings.ToLower(m.Text), q) {
			score += 0.5
		}
		if score <= 0 && strings.TrimSpace(req.Query) != "" {
			continue
		}
		results = append(results, SearchResult{Memory: m, Score: score})
	}

	sort.Slice(results, func(i, j int) bool {
		if results[i].Score == results[j].Score {
			return results[i].CreatedAt.After(results[j].CreatedAt)
		}
		return results[i].Score > results[j].Score
	})

	if len(results) > limit {
		results = results[:limit]
	}
	return results, nil
}

func (s *MemoryService) Timeline(_ context.Context, req TimelineRequest) ([]Memory, error) {
	branch := defaultBranch(req.BranchName)
	limit := req.Limit
	if limit <= 0 {
		limit = 20
	}

	s.mu.RLock()
	items := make([]Memory, 0, len(s.memories))
	for _, m := range s.memories {
		if !matchMemoryFilter(m, branch, req.Category, req.SourceType, "", req.SessionID, false) {
			continue
		}
		items = append(items, cloneMemory(m))
	}
	s.mu.RUnlock()

	sort.Slice(items, func(i, j int) bool {
		return items[i].CreatedAt.After(items[j].CreatedAt)
	})
	if len(items) > limit {
		items = items[:limit]
	}
	return items, nil
}

func (s *MemoryService) Count(_ context.Context, branchName string, includeArchived bool) (int, error) {
	branch := defaultBranch(branchName)
	s.mu.RLock()
	defer s.mu.RUnlock()
	count := 0
	for _, m := range s.memories {
		if m.BranchName != branch {
			continue
		}
		if !includeArchived && m.Status == "archived" {
			continue
		}
		count++
	}
	return count, nil
}

func (s *MemoryService) CreateBranch(ctx context.Context, name, parent, description string) (Branch, error) {
	name = strings.TrimSpace(name)
	if name == "" {
		return Branch{}, fmt.Errorf("%w: branch name required", ErrInvalidInput)
	}
	if parent == "" {
		parent = "main"
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.branches[name]; ok {
		return Branch{}, fmt.Errorf("%w: %s", ErrBranchExists, name)
	}
	if _, ok := s.branches[parent]; !ok {
		return Branch{}, fmt.Errorf("%w: %s", ErrBranchNotFound, parent)
	}

	now := time.Now().UTC()
	branch := Branch{
		Name:        name,
		Parent:      parent,
		Description: description,
		Status:      "active",
		CreatedAt:   now,
		UpdatedAt:   now,
	}
	if err := s.persistBranch(ctx, branch); err != nil {
		return Branch{}, err
	}
	s.branches[name] = branch
	return branch, nil
}

func (s *MemoryService) SwitchBranch(_ context.Context, name string) (Branch, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	branch, ok := s.branches[name]
	if !ok {
		return Branch{}, fmt.Errorf("%w: %s", ErrBranchNotFound, name)
	}
	if branch.Status == "archived" {
		return Branch{}, fmt.Errorf("%w: branch is archived", ErrInvalidBranch)
	}
	return branch, nil
}

func (s *MemoryService) ListBranches(_ context.Context) ([]Branch, error) {
	s.mu.RLock()
	defer s.mu.RUnlock()
	out := make([]Branch, 0, len(s.branches))
	for _, branch := range s.branches {
		out = append(out, branch)
	}
	sort.Slice(out, func(i, j int) bool {
		return out[i].Name < out[j].Name
	})
	return out, nil
}

func (s *MemoryService) ArchiveBranch(ctx context.Context, name string) (Branch, error) {
	if name == "main" {
		return Branch{}, fmt.Errorf("%w: cannot archive main branch", ErrInvalidBranch)
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	branch, ok := s.branches[name]
	if !ok {
		return Branch{}, fmt.Errorf("%w: %s", ErrBranchNotFound, name)
	}
	branch.Status = "archived"
	branch.UpdatedAt = time.Now().UTC()
	if err := s.persistBranch(ctx, branch); err != nil {
		return Branch{}, err
	}
	s.branches[name] = branch
	return branch, nil
}

func (s *MemoryService) DeleteBranch(ctx context.Context, name string) error {
	if name == "main" {
		return fmt.Errorf("%w: cannot delete main branch", ErrInvalidBranch)
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.branches[name]; !ok {
		return fmt.Errorf("%w: %s", ErrBranchNotFound, name)
	}
	now := time.Now().UTC()
	for id, m := range s.memories {
		if m.BranchName != name {
			continue
		}
		m.Status = "archived"
		m.UpdatedAt = now
		if err := s.persistMemory(ctx, m); err != nil {
			return err
		}
		s.memories[id] = m
	}
	if err := s.deleteBranch(ctx, name); err != nil {
		return err
	}
	delete(s.branches, name)
	return nil
}

func (s *MemoryService) Snapshot(ctx context.Context, branch, label string) (Snapshot, error) {
	branch = defaultBranch(branch)
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.branches[branch]; !ok {
		return Snapshot{}, fmt.Errorf("%w: %s", ErrBranchNotFound, branch)
	}
	snapshot := Snapshot{
		ID:        uuid.NewString(),
		Branch:    branch,
		Label:     label,
		CreatedAt: time.Now().UTC(),
	}
	if err := s.persistSnapshot(ctx, snapshot); err != nil {
		return Snapshot{}, err
	}
	s.snapshots[snapshot.ID] = snapshot
	return snapshot, nil
}

func (s *MemoryService) ListSnapshots(_ context.Context, branch string) ([]Snapshot, error) {
	branch = defaultBranch(branch)
	s.mu.RLock()
	defer s.mu.RUnlock()
	items := make([]Snapshot, 0)
	for _, snapshot := range s.snapshots {
		if snapshot.Branch != branch {
			continue
		}
		items = append(items, snapshot)
	}
	sort.Slice(items, func(i, j int) bool {
		return items[i].CreatedAt.After(items[j].CreatedAt)
	})
	return items, nil
}

func (s *MemoryService) Restore(ctx context.Context, snapshotID string) (int, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	snapshot, ok := s.snapshots[snapshotID]
	if !ok {
		return 0, fmt.Errorf("%w: %s", ErrSnapshotNotFound, snapshotID)
	}

	now := time.Now().UTC()
	archived := 0
	for id, m := range s.memories {
		if m.BranchName != snapshot.Branch || m.Status == "archived" {
			continue
		}
		if m.CreatedAt.After(snapshot.CreatedAt) {
			m.Status = "archived"
			m.UpdatedAt = now
			if err := s.persistMemory(ctx, m); err != nil {
				return archived, err
			}
			s.memories[id] = m
			archived++
		}
	}
	return archived, nil
}

func (s *MemoryService) Merge(ctx context.Context, sourceBranch, targetBranch string) (MergeResult, error) {
	sourceBranch = defaultBranch(sourceBranch)
	targetBranch = defaultBranch(targetBranch)
	if sourceBranch == targetBranch {
		return MergeResult{}, fmt.Errorf("%w: source and target branch must differ", ErrInvalidInput)
	}

	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.branches[sourceBranch]; !ok {
		return MergeResult{}, fmt.Errorf("%w: %s", ErrBranchNotFound, sourceBranch)
	}
	if _, ok := s.branches[targetBranch]; !ok {
		return MergeResult{}, fmt.Errorf("%w: %s", ErrBranchNotFound, targetBranch)
	}

	targetTexts := make(map[string]struct{})
	for _, m := range s.memories {
		if m.BranchName == targetBranch && m.Status != "archived" {
			targetTexts[m.Text] = struct{}{}
		}
	}

	merged := 0
	skipped := 0
	now := time.Now().UTC()
	for _, m := range s.memories {
		if m.BranchName != sourceBranch || m.Status == "archived" {
			continue
		}
		if _, dup := targetTexts[m.Text]; dup {
			skipped++
			continue
		}
		copy := cloneMemory(m)
		copy.ID = uuid.NewString()
		copy.BranchName = targetBranch
		copy.CreatedAt = now
		copy.UpdatedAt = now
		if err := s.persistMemory(ctx, copy); err != nil {
			return MergeResult{}, err
		}
		s.memories[copy.ID] = copy
		targetTexts[copy.Text] = struct{}{}
		merged++
	}

	return MergeResult{SourceBranch: sourceBranch, TargetBranch: targetBranch, Merged: merged, Skipped: skipped}, nil
}

func (s *MemoryService) Relate(ctx context.Context, sourceID, targetID, relationType string, weight float64, metadata map[string]any) (Relation, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.memories[sourceID]; !ok {
		return Relation{}, fmt.Errorf("%w: source memory %s", ErrMemoryNotFound, sourceID)
	}
	if _, ok := s.memories[targetID]; !ok {
		return Relation{}, fmt.Errorf("%w: target memory %s", ErrMemoryNotFound, targetID)
	}
	if relationType == "" {
		relationType = "related_to"
	}
	if weight == 0 {
		weight = 1.0
	}
	relation := Relation{
		ID:           uuid.NewString(),
		SourceID:     sourceID,
		TargetID:     targetID,
		RelationType: relationType,
		Weight:       weight,
		Metadata:     cloneMap(metadata),
		CreatedAt:    time.Now().UTC(),
	}
	if err := s.persistRelation(ctx, relation); err != nil {
		return Relation{}, err
	}
	s.relations[relation.ID] = relation
	return relation, nil
}

func (s *MemoryService) Relations(_ context.Context, memoryID, relationType, direction string) ([]Relation, error) {
	if direction == "" {
		direction = "both"
	}

	s.mu.RLock()
	defer s.mu.RUnlock()
	out := make([]Relation, 0)
	for _, rel := range s.relations {
		if relationType != "" && rel.RelationType != relationType {
			continue
		}
		matches := false
		switch direction {
		case "incoming":
			matches = rel.TargetID == memoryID
		case "outgoing":
			matches = rel.SourceID == memoryID
		default:
			matches = rel.SourceID == memoryID || rel.TargetID == memoryID
		}
		if matches {
			out = append(out, rel)
		}
	}
	sort.Slice(out, func(i, j int) bool { return out[i].CreatedAt.After(out[j].CreatedAt) })
	return out, nil
}

func (s *MemoryService) DeleteRelation(ctx context.Context, relationID string) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	if _, ok := s.relations[relationID]; !ok {
		return fmt.Errorf("%w: %s", ErrRelationNotFound, relationID)
	}
	if err := s.deleteRelation(ctx, relationID); err != nil {
		return err
	}
	delete(s.relations, relationID)
	return nil
}

func (s *MemoryService) Graph(ctx context.Context, memoryID string, depth, limit int) (GraphResult, error) {
	if depth <= 0 {
		depth = 1
	}
	if limit <= 0 {
		limit = 50
	}

	root, err := s.Get(ctx, memoryID)
	if err != nil {
		return GraphResult{}, err
	}

	s.mu.RLock()
	defer s.mu.RUnlock()
	visited := map[string]struct{}{root.ID: {}}
	nodes := []Memory{root}
	edges := []Relation{}
	type queueItem struct {
		id    string
		depth int
	}
	queue := []queueItem{{id: root.ID, depth: 0}}

	for len(queue) > 0 && len(nodes) < limit {
		item := queue[0]
		queue = queue[1:]
		if item.depth >= depth {
			continue
		}
		for _, rel := range s.relations {
			var nextID string
			switch {
			case rel.SourceID == item.id:
				nextID = rel.TargetID
			case rel.TargetID == item.id:
				nextID = rel.SourceID
			default:
				continue
			}
			edges = append(edges, rel)
			if _, seen := visited[nextID]; seen {
				continue
			}
			nextMem, ok := s.memories[nextID]
			if !ok {
				continue
			}
			visited[nextID] = struct{}{}
			nodes = append(nodes, cloneMemory(nextMem))
			queue = append(queue, queueItem{id: nextID, depth: item.depth + 1})
			if len(nodes) >= limit {
				break
			}
		}
	}

	return GraphResult{Root: root.ID, Depth: depth, Nodes: nodes, Edges: edges}, nil
}

func (s *MemoryService) persistMemory(ctx context.Context, memory Memory) error {
	if s.store == nil {
		return nil
	}
	if err := s.store.UpsertMemory(ctx, memory); err != nil {
		return fmt.Errorf("persist memory %s: %w", memory.ID, err)
	}
	return nil
}

func (s *MemoryService) persistBranch(ctx context.Context, branch Branch) error {
	if s.store == nil {
		return nil
	}
	if err := s.store.UpsertBranch(ctx, branch); err != nil {
		return fmt.Errorf("persist branch %s: %w", branch.Name, err)
	}
	return nil
}

func (s *MemoryService) deleteBranch(ctx context.Context, branchName string) error {
	if s.store == nil {
		return nil
	}
	if err := s.store.DeleteBranch(ctx, branchName); err != nil {
		return fmt.Errorf("delete branch %s: %w", branchName, err)
	}
	return nil
}

func (s *MemoryService) persistSnapshot(ctx context.Context, snapshot Snapshot) error {
	if s.store == nil {
		return nil
	}
	if err := s.store.UpsertSnapshot(ctx, snapshot); err != nil {
		return fmt.Errorf("persist snapshot %s: %w", snapshot.ID, err)
	}
	return nil
}

func (s *MemoryService) persistRelation(ctx context.Context, relation Relation) error {
	if s.store == nil {
		return nil
	}
	if err := s.store.UpsertRelation(ctx, relation); err != nil {
		return fmt.Errorf("persist relation %s: %w", relation.ID, err)
	}
	return nil
}

func (s *MemoryService) deleteRelation(ctx context.Context, relationID string) error {
	if s.store == nil {
		return nil
	}
	if err := s.store.DeleteRelation(ctx, relationID); err != nil {
		return fmt.Errorf("delete relation %s: %w", relationID, err)
	}
	return nil
}

func defaultStatus(status string) string {
	if strings.TrimSpace(status) == "" {
		return "active"
	}
	return status
}

func defaultBranch(branch string) string {
	if strings.TrimSpace(branch) == "" {
		return "main"
	}
	return branch
}

func cloneMemory(memory Memory) Memory {
	copy := memory
	if memory.Embedding != nil {
		copy.Embedding = append([]float32(nil), memory.Embedding...)
	}
	copy.Metadata = cloneMap(memory.Metadata)
	return copy
}

func cloneMap(in map[string]any) map[string]any {
	if in == nil {
		return nil
	}
	out := make(map[string]any, len(in))
	for k, v := range in {
		out[k] = v
	}
	return out
}

func matchMemoryFilter(m Memory, branch, category, sourceType, status, sessionID string, includeArchived bool) bool {
	if m.BranchName != branch {
		return false
	}
	if category != "" && m.Category != category {
		return false
	}
	if sourceType != "" && m.SourceType != sourceType {
		return false
	}
	if status != "" && m.Status != status {
		return false
	}
	if status == "" && !includeArchived && m.Status == "archived" {
		return false
	}
	if sessionID != "" && m.SessionID != sessionID {
		return false
	}
	return true
}

func toSearchResults(memories []Memory, limit int) []SearchResult {
	results := make([]SearchResult, 0, len(memories))
	for i, m := range memories {
		if i >= limit {
			break
		}
		results = append(results, SearchResult{Memory: m, Score: 0.0})
	}
	return results
}

func cosineSimilarity(a, b []float32) float64 {
	if len(a) == 0 || len(b) == 0 {
		return 0
	}
	minLen := len(a)
	if len(b) < minLen {
		minLen = len(b)
	}
	dot := 0.0
	normA := 0.0
	normB := 0.0
	for i := 0; i < minLen; i++ {
		av := float64(a[i])
		bv := float64(b[i])
		dot += av * bv
		normA += av * av
		normB += bv * bv
	}
	if normA == 0 || normB == 0 {
		return 0
	}
	return dot / (math.Sqrt(normA) * math.Sqrt(normB))
}
