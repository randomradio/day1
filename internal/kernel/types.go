package kernel

import (
	"context"
	"time"
)

// Memory is the durable memory unit.
type Memory struct {
	ID          string         `json:"id"`
	UserID      string         `json:"user_id,omitempty"`
	Text        string         `json:"text"`
	Context     string         `json:"context,omitempty"`
	FileContext string         `json:"file_context,omitempty"`
	SessionID   string         `json:"session_id,omitempty"`
	TraceID     string         `json:"trace_id,omitempty"`
	Category    string         `json:"category,omitempty"`
	SourceType  string         `json:"source_type,omitempty"`
	Status      string         `json:"status"`
	BranchName  string         `json:"branch_name"`
	Confidence  float64        `json:"confidence,omitempty"`
	Embedding   []float32      `json:"-"`
	Metadata    map[string]any `json:"metadata,omitempty"`
	CreatedAt   time.Time      `json:"created_at"`
	UpdatedAt   time.Time      `json:"updated_at"`
}

type WriteRequest struct {
	Text        string         `json:"text"`
	UserID      string         `json:"user_id,omitempty"`
	Context     string         `json:"context,omitempty"`
	FileContext string         `json:"file_context,omitempty"`
	SessionID   string         `json:"session_id,omitempty"`
	TraceID     string         `json:"trace_id,omitempty"`
	Category    string         `json:"category,omitempty"`
	SourceType  string         `json:"source_type,omitempty"`
	Status      string         `json:"status,omitempty"`
	BranchName  string         `json:"branch_name,omitempty"`
	Confidence  float64        `json:"confidence,omitempty"`
	Metadata    map[string]any `json:"metadata,omitempty"`
}

type UpdateRequest struct {
	MemoryID    string         `json:"memory_id"`
	UserID      string         `json:"user_id,omitempty"`
	Text        *string        `json:"text,omitempty"`
	Context     *string        `json:"context,omitempty"`
	FileContext *string        `json:"file_context,omitempty"`
	Category    *string        `json:"category,omitempty"`
	SourceType  *string        `json:"source_type,omitempty"`
	Status      *string        `json:"status,omitempty"`
	Confidence  *float64       `json:"confidence,omitempty"`
	Metadata    map[string]any `json:"metadata,omitempty"`
}

type SearchRequest struct {
	Query      string `json:"query"`
	BranchName string `json:"branch_name,omitempty"`
	Category   string `json:"category,omitempty"`
	SourceType string `json:"source_type,omitempty"`
	Status     string `json:"status,omitempty"`
	SessionID  string `json:"session_id,omitempty"`
	Limit      int    `json:"limit,omitempty"`
}

type SearchResult struct {
	Memory
	Score float64 `json:"score"`
}

type TimelineRequest struct {
	BranchName string `json:"branch_name,omitempty"`
	Category   string `json:"category,omitempty"`
	SourceType string `json:"source_type,omitempty"`
	SessionID  string `json:"session_id,omitempty"`
	Limit      int    `json:"limit,omitempty"`
}

type Branch struct {
	Name        string    `json:"branch_name"`
	UserID      string    `json:"user_id,omitempty"`
	Parent      string    `json:"parent_branch,omitempty"`
	Description string    `json:"description,omitempty"`
	Status      string    `json:"status"`
	CreatedAt   time.Time `json:"created_at"`
	UpdatedAt   time.Time `json:"updated_at"`
}

type Snapshot struct {
	ID        string    `json:"snapshot_id"`
	UserID    string    `json:"user_id,omitempty"`
	Branch    string    `json:"branch"`
	Label     string    `json:"label,omitempty"`
	CreatedAt time.Time `json:"created_at"`
}

type MergeResult struct {
	SourceBranch string `json:"source_branch"`
	TargetBranch string `json:"target_branch"`
	Merged       int    `json:"merged"`
	Skipped      int    `json:"skipped"`
}

type Relation struct {
	ID           string         `json:"id"`
	UserID       string         `json:"user_id,omitempty"`
	SourceID     string         `json:"source_id"`
	TargetID     string         `json:"target_id"`
	RelationType string         `json:"relation_type"`
	Weight       float64        `json:"weight"`
	Metadata     map[string]any `json:"metadata,omitempty"`
	CreatedAt    time.Time      `json:"created_at"`
}

type GraphResult struct {
	Root  string     `json:"root"`
	Depth int        `json:"depth"`
	Nodes []Memory   `json:"nodes"`
	Edges []Relation `json:"edges"`
}

// EmbeddingProvider generates vectors for semantic retrieval.
type EmbeddingProvider interface {
	Embed(ctx context.Context, text string) ([]float32, error)
	EmbedBatch(ctx context.Context, texts []string) ([][]float32, error)
}

// LLMProvider is used by evolution/comparison modules.
type LLMProvider interface {
	Complete(ctx context.Context, prompt string) (string, error)
}

// MemoryKernel defines core memory-kernel capabilities.
type MemoryKernel interface {
	Write(ctx context.Context, req WriteRequest) (Memory, error)
	WriteBatch(ctx context.Context, reqs []WriteRequest) ([]Memory, error)
	Get(ctx context.Context, memoryID string) (Memory, error)
	Update(ctx context.Context, req UpdateRequest) (Memory, error)
	Archive(ctx context.Context, memoryID string) (Memory, error)
	ArchiveBatch(ctx context.Context, memoryIDs []string) (int, error)
	Search(ctx context.Context, req SearchRequest) ([]SearchResult, error)
	Timeline(ctx context.Context, req TimelineRequest) ([]Memory, error)
	Count(ctx context.Context, branchName string, includeArchived bool) (int, error)

	CreateBranch(ctx context.Context, name, parent, description string) (Branch, error)
	SwitchBranch(ctx context.Context, name string) (Branch, error)
	ListBranches(ctx context.Context) ([]Branch, error)
	ArchiveBranch(ctx context.Context, name string) (Branch, error)
	DeleteBranch(ctx context.Context, name string) error

	Snapshot(ctx context.Context, branch, label string) (Snapshot, error)
	ListSnapshots(ctx context.Context, branch string) ([]Snapshot, error)
	Restore(ctx context.Context, snapshotID string) (int, error)
	Merge(ctx context.Context, sourceBranch, targetBranch string) (MergeResult, error)

	Relate(ctx context.Context, sourceID, targetID, relationType string, weight float64, metadata map[string]any) (Relation, error)
	Relations(ctx context.Context, memoryID, relationType, direction string) ([]Relation, error)
	DeleteRelation(ctx context.Context, relationID string) error
	Graph(ctx context.Context, memoryID string, depth, limit int) (GraphResult, error)
}
