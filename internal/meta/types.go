package meta

import "time"

// Session tracks high-level per-session counters and lifecycle.
type Session struct {
	ID          string
	BranchName  string
	Status      string
	StartedAt   time.Time
	EndedAt     *time.Time
	MemoryCount int
	TraceCount  int
	HookCount   int
}

// HookLog stores append-only hook events and payload.
type HookLog struct {
	Seq       int64
	Event     string
	SessionID string
	Payload   map[string]any
	CreatedAt time.Time
}

// Trace stores trace playback payload.
type Trace struct {
	ID              string
	SessionID       string
	BranchName      string
	TraceType       string
	ParentTraceID   string
	SkillID         string
	TaskDescription string
	Steps           []map[string]any
	Metadata        map[string]any
	CreatedAt       time.Time
}

// Comparison stores trace comparison results.
type Comparison struct {
	ID              string
	TraceAID        string
	TraceBID        string
	SkillID         string
	DimensionScores map[string]float64
	Verdict         string
	Insights        map[string]any
	CreatedAt       time.Time
}

// PersistedState is the full API metadata snapshot.
type PersistedState struct {
	Sessions    []Session
	HookLogs    []HookLog
	Traces      []Trace
	Comparisons []Comparison
}
