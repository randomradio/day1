package storage

import (
	"context"
	"regexp"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"

	"day1/internal/meta"
)

func newMockStore(t *testing.T) (*MySQLStore, sqlmock.Sqlmock, func()) {
	t.Helper()
	db, mock, err := sqlmock.New(sqlmock.QueryMatcherOption(sqlmock.QueryMatcherRegexp))
	if err != nil {
		t.Fatalf("sqlmock new: %v", err)
	}
	cleanup := func() { _ = db.Close() }
	return &MySQLStore{db: db}, mock, cleanup
}

func TestEnsureMetaSchema(t *testing.T) {
	store, mock, cleanup := newMockStore(t)
	defer cleanup()

	for i := 0; i < 4; i++ {
		mock.ExpectExec(regexp.QuoteMeta("CREATE TABLE IF NOT EXISTS")).WillReturnResult(sqlmock.NewResult(0, 0))
	}

	if err := store.EnsureMetaSchema(context.Background()); err != nil {
		t.Fatalf("ensure meta schema failed: %v", err)
	}
	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("unmet expectations: %v", err)
	}
}

func TestUpsertSessionAndMetaWrites(t *testing.T) {
	store, mock, cleanup := newMockStore(t)
	defer cleanup()

	now := time.Now().UTC()
	mock.ExpectExec("INSERT INTO sessions").WithArgs(
		"s1", "main", "active", sqlmock.AnyArg(), nil, 2, 1, 3,
	).WillReturnResult(sqlmock.NewResult(0, 1))

	err := store.UpsertSession(context.Background(), meta.Session{
		ID:          "s1",
		BranchName:  "main",
		Status:      "active",
		StartedAt:   now,
		MemoryCount: 2,
		TraceCount:  1,
		HookCount:   3,
	})
	if err != nil {
		t.Fatalf("upsert session failed: %v", err)
	}

	mock.ExpectExec("INSERT INTO hook_logs").WithArgs(
		"SessionStart", "s1", sqlmock.AnyArg(), sqlmock.AnyArg(),
	).WillReturnResult(sqlmock.NewResult(42, 1))

	seq, err := store.InsertHookLog(context.Background(), meta.HookLog{
		Event:     "SessionStart",
		SessionID: "s1",
		Payload:   map[string]any{"k": "v"},
		CreatedAt: now,
	})
	if err != nil {
		t.Fatalf("insert hook failed: %v", err)
	}
	if seq != 42 {
		t.Fatalf("expected seq 42, got %d", seq)
	}

	mock.ExpectExec("INSERT INTO traces").WithArgs(
		"t1", "s1", "main", "original", nil, nil, nil, sqlmock.AnyArg(), nil, sqlmock.AnyArg(),
	).WillReturnResult(sqlmock.NewResult(0, 1))

	err = store.UpsertTrace(context.Background(), meta.Trace{
		ID:         "t1",
		SessionID:  "s1",
		BranchName: "main",
		TraceType:  "original",
		Steps:      []map[string]any{{"event": "start"}},
		CreatedAt:  now,
	})
	if err != nil {
		t.Fatalf("upsert trace failed: %v", err)
	}

	mock.ExpectExec("INSERT INTO trace_comparisons").WithArgs(
		"c1", "t1", "t2", nil, sqlmock.AnyArg(), "different", sqlmock.AnyArg(), sqlmock.AnyArg(),
	).WillReturnResult(sqlmock.NewResult(0, 1))

	err = store.UpsertComparison(context.Background(), meta.Comparison{
		ID:              "c1",
		TraceAID:        "t1",
		TraceBID:        "t2",
		Verdict:         "different",
		DimensionScores: map[string]float64{"step_similarity": 0.5},
		Insights:        map[string]any{"avg": 0.5},
		CreatedAt:       now,
	})
	if err != nil {
		t.Fatalf("upsert comparison failed: %v", err)
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("unmet expectations: %v", err)
	}
}

func TestLoadMetaState(t *testing.T) {
	store, mock, cleanup := newMockStore(t)
	defer cleanup()

	now := time.Now().UTC()
	ended := now.Add(10 * time.Minute)

	sessionRows := sqlmock.NewRows([]string{"id", "branch_name", "status", "started_at", "ended_at", "memory_count", "trace_count", "hook_count"}).
		AddRow("s1", "main", "active", now, ended, 1, 2, 3)
	mock.ExpectQuery("SELECT id, branch_name, status, started_at, ended_at, memory_count, trace_count, hook_count").WillReturnRows(sessionRows)

	hookRows := sqlmock.NewRows([]string{"seq", "event", "session_id", "payload_json", "created_at"}).
		AddRow(int64(1), "SessionStart", "s1", `{"k":"v"}`, now)
	mock.ExpectQuery("SELECT seq, event, session_id, payload_json, created_at").WillReturnRows(hookRows)

	traceRows := sqlmock.NewRows([]string{"id", "session_id", "branch_name", "trace_type", "parent_trace_id", "skill_id", "task_description", "steps_json", "metadata_json", "created_at"}).
		AddRow("t1", "s1", "main", "original", nil, nil, nil, `[{"event":"x"}]`, `{"m":1}`, now)
	mock.ExpectQuery("SELECT id, session_id, branch_name, trace_type, parent_trace_id, skill_id, task_description, steps_json, metadata_json, created_at").WillReturnRows(traceRows)

	comparisonRows := sqlmock.NewRows([]string{"id", "trace_a_id", "trace_b_id", "skill_id", "dimension_scores_json", "verdict", "insights_json", "created_at"}).
		AddRow("c1", "t1", "t2", nil, `{"step_similarity":0.5}`, "different", `{"avg":0.5}`, now)
	mock.ExpectQuery("SELECT id, trace_a_id, trace_b_id, skill_id, dimension_scores_json, verdict, insights_json, created_at").WillReturnRows(comparisonRows)

	state, err := store.LoadMetaState(context.Background())
	if err != nil {
		t.Fatalf("load meta state failed: %v", err)
	}
	if len(state.Sessions) != 1 || len(state.HookLogs) != 1 || len(state.Traces) != 1 || len(state.Comparisons) != 1 {
		t.Fatalf("unexpected loaded state counts: %+v", state)
	}
	if state.Sessions[0].ID != "s1" {
		t.Fatalf("unexpected session id: %s", state.Sessions[0].ID)
	}
	if state.Traces[0].ID != "t1" {
		t.Fatalf("unexpected trace id: %s", state.Traces[0].ID)
	}

	if err := mock.ExpectationsWereMet(); err != nil {
		t.Fatalf("unmet expectations: %v", err)
	}
}
