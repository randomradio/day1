package kernel

import "context"

// PersistedState is a full snapshot of kernel state loaded from durable storage.
type PersistedState struct {
	Memories  []Memory
	Branches  []Branch
	Snapshots []Snapshot
	Relations []Relation
}

// StateStore persists kernel state to a durable backend (MatrixOne-compatible SQL).
type StateStore interface {
	EnsureSchema(ctx context.Context) error
	LoadState(ctx context.Context) (PersistedState, error)
	UpsertMemory(ctx context.Context, memory Memory) error
	UpsertBranch(ctx context.Context, branch Branch) error
	DeleteBranch(ctx context.Context, userID, branchName string) error
	UpsertSnapshot(ctx context.Context, snapshot Snapshot) error
	UpsertRelation(ctx context.Context, relation Relation) error
	DeleteRelation(ctx context.Context, relationID string) error
}
