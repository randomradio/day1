package storage

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"strings"
	"time"

	_ "github.com/go-sql-driver/mysql"

	"day1/internal/kernel"
	"day1/internal/meta"
)

// MySQLStore stores kernel state in MatrixOne/MySQL-compatible SQL tables.
type MySQLStore struct {
	db *sql.DB
}

func NewMySQLStoreFromURL(databaseURL string) (*MySQLStore, error) {
	dsn, err := ParseDatabaseURL(databaseURL)
	if err != nil {
		return nil, err
	}
	db, err := sql.Open("mysql", dsn)
	if err != nil {
		return nil, fmt.Errorf("open mysql store: %w", err)
	}
	db.SetMaxOpenConns(10)
	db.SetMaxIdleConns(5)
	db.SetConnMaxLifetime(30 * time.Minute)
	if err := db.Ping(); err != nil {
		_ = db.Close()
		return nil, fmt.Errorf("ping mysql store: %w", err)
	}
	return &MySQLStore{db: db}, nil
}

func (s *MySQLStore) Close() error {
	if s == nil || s.db == nil {
		return nil
	}
	return s.db.Close()
}

func (s *MySQLStore) EnsureSchema(ctx context.Context) error {
	stmts := []string{
		`CREATE TABLE IF NOT EXISTS memories (
			id VARCHAR(36) PRIMARY KEY,
			user_id VARCHAR(200) NOT NULL DEFAULT '',
			text TEXT NOT NULL,
			context TEXT NULL,
			file_context VARCHAR(500) NULL,
			session_id VARCHAR(200) NULL,
			trace_id VARCHAR(64) NULL,
			category VARCHAR(100) NULL,
			source_type VARCHAR(100) NULL,
			status VARCHAR(20) NOT NULL,
			branch_name VARCHAR(100) NOT NULL,
			confidence DOUBLE NULL,
			embedding_json LONGTEXT NULL,
			metadata_json LONGTEXT NULL,
			created_at DATETIME(6) NOT NULL,
			updated_at DATETIME(6) NOT NULL,
			INDEX idx_mem_user (user_id),
			INDEX idx_mem_branch (branch_name),
			INDEX idx_mem_session (session_id),
			INDEX idx_mem_trace (trace_id),
			INDEX idx_mem_created (created_at),
			INDEX idx_mem_status (status)
		)`,
		`CREATE TABLE IF NOT EXISTS branches (
			user_id VARCHAR(200) NOT NULL DEFAULT '',
			name VARCHAR(100) NOT NULL,
			parent VARCHAR(100) NULL,
			description TEXT NULL,
			status VARCHAR(20) NOT NULL,
			created_at DATETIME(6) NOT NULL,
			updated_at DATETIME(6) NOT NULL,
			PRIMARY KEY (user_id, name),
			INDEX idx_branch_user (user_id),
			INDEX idx_branch_status (status)
		)`,
		`CREATE TABLE IF NOT EXISTS snapshots (
			id VARCHAR(36) PRIMARY KEY,
			user_id VARCHAR(200) NOT NULL DEFAULT '',
			branch_name VARCHAR(100) NOT NULL,
			label VARCHAR(200) NULL,
			created_at DATETIME(6) NOT NULL,
			INDEX idx_snap_user_branch (user_id, branch_name),
			INDEX idx_snap_branch (branch_name)
		)`,
		`CREATE TABLE IF NOT EXISTS memory_relations (
			id VARCHAR(36) PRIMARY KEY,
			user_id VARCHAR(200) NOT NULL DEFAULT '',
			source_id VARCHAR(36) NOT NULL,
			target_id VARCHAR(36) NOT NULL,
			relation_type VARCHAR(100) NOT NULL,
			weight DOUBLE NOT NULL,
			metadata_json LONGTEXT NULL,
			created_at DATETIME(6) NOT NULL,
			INDEX idx_rel_user (user_id),
			INDEX idx_rel_source (source_id),
			INDEX idx_rel_target (target_id),
			INDEX idx_rel_type (relation_type)
		)`,
	}
	for _, stmt := range stmts {
		if _, err := s.db.ExecContext(ctx, stmt); err != nil {
			return fmt.Errorf("ensure schema: %w", err)
		}
	}
	alterStmts := []string{
		"ALTER TABLE memories ADD COLUMN user_id VARCHAR(200) NOT NULL DEFAULT ''",
		"ALTER TABLE branches ADD COLUMN user_id VARCHAR(200) NOT NULL DEFAULT ''",
		"ALTER TABLE snapshots ADD COLUMN user_id VARCHAR(200) NOT NULL DEFAULT ''",
		"ALTER TABLE memory_relations ADD COLUMN user_id VARCHAR(200) NOT NULL DEFAULT ''",
		"CREATE INDEX idx_mem_user ON memories (user_id)",
		"CREATE INDEX idx_branch_user ON branches (user_id)",
		"CREATE INDEX idx_snap_user_branch ON snapshots (user_id, branch_name)",
		"CREATE INDEX idx_rel_user ON memory_relations (user_id)",
	}
	for _, stmt := range alterStmts {
		if _, err := s.db.ExecContext(ctx, stmt); err != nil && !isDuplicateDDL(err) {
			return fmt.Errorf("ensure schema migration: %w", err)
		}
	}
	return nil
}

func (s *MySQLStore) LoadState(ctx context.Context) (kernel.PersistedState, error) {
	state := kernel.PersistedState{
		Memories:  []kernel.Memory{},
		Branches:  []kernel.Branch{},
		Snapshots: []kernel.Snapshot{},
		Relations: []kernel.Relation{},
	}

	memRows, err := s.db.QueryContext(ctx, `
		SELECT id, user_id, text, context, file_context, session_id, trace_id, category, source_type, status,
		       branch_name, confidence, embedding_json, metadata_json, created_at, updated_at
		FROM memories`)
	if err != nil {
		return state, fmt.Errorf("load memories: %w", err)
	}
	defer memRows.Close()
	for memRows.Next() {
		var (
			id, userID, text, status, branch                           string
			ctxText, fileCtx, sessionID, traceID, category, sourceType sql.NullString
			confidence                                                 sql.NullFloat64
			embeddingJSON, metadataJSON                                sql.NullString
			createdAt, updatedAt                                       time.Time
		)
		if err := memRows.Scan(&id, &userID, &text, &ctxText, &fileCtx, &sessionID, &traceID, &category, &sourceType, &status, &branch, &confidence, &embeddingJSON, &metadataJSON, &createdAt, &updatedAt); err != nil {
			return state, fmt.Errorf("scan memory: %w", err)
		}
		memory := kernel.Memory{
			ID:          id,
			UserID:      userID,
			Text:        text,
			Context:     ctxText.String,
			FileContext: fileCtx.String,
			SessionID:   sessionID.String,
			TraceID:     traceID.String,
			Category:    category.String,
			SourceType:  sourceType.String,
			Status:      status,
			BranchName:  branch,
			CreatedAt:   createdAt.UTC(),
			UpdatedAt:   updatedAt.UTC(),
		}
		if confidence.Valid {
			memory.Confidence = confidence.Float64
		}
		if embeddingJSON.Valid && embeddingJSON.String != "" {
			_ = json.Unmarshal([]byte(embeddingJSON.String), &memory.Embedding)
		}
		if metadataJSON.Valid && metadataJSON.String != "" {
			_ = json.Unmarshal([]byte(metadataJSON.String), &memory.Metadata)
		}
		state.Memories = append(state.Memories, memory)
	}

	branchRows, err := s.db.QueryContext(ctx, `SELECT user_id, name, parent, description, status, created_at, updated_at FROM branches`)
	if err != nil {
		return state, fmt.Errorf("load branches: %w", err)
	}
	defer branchRows.Close()
	for branchRows.Next() {
		var userID, name, status string
		var parent, description sql.NullString
		var createdAt, updatedAt time.Time
		if err := branchRows.Scan(&userID, &name, &parent, &description, &status, &createdAt, &updatedAt); err != nil {
			return state, fmt.Errorf("scan branch: %w", err)
		}
		state.Branches = append(state.Branches, kernel.Branch{
			Name:        name,
			UserID:      userID,
			Parent:      parent.String,
			Description: description.String,
			Status:      status,
			CreatedAt:   createdAt.UTC(),
			UpdatedAt:   updatedAt.UTC(),
		})
	}

	snapshotRows, err := s.db.QueryContext(ctx, `SELECT id, user_id, branch_name, label, created_at FROM snapshots`)
	if err != nil {
		return state, fmt.Errorf("load snapshots: %w", err)
	}
	defer snapshotRows.Close()
	for snapshotRows.Next() {
		var id, userID, branch string
		var label sql.NullString
		var createdAt time.Time
		if err := snapshotRows.Scan(&id, &userID, &branch, &label, &createdAt); err != nil {
			return state, fmt.Errorf("scan snapshot: %w", err)
		}
		state.Snapshots = append(state.Snapshots, kernel.Snapshot{ID: id, UserID: userID, Branch: branch, Label: label.String, CreatedAt: createdAt.UTC()})
	}

	relRows, err := s.db.QueryContext(ctx, `SELECT id, user_id, source_id, target_id, relation_type, weight, metadata_json, created_at FROM memory_relations`)
	if err != nil {
		return state, fmt.Errorf("load relations: %w", err)
	}
	defer relRows.Close()
	for relRows.Next() {
		var id, userID, sourceID, targetID, relType string
		var weight float64
		var metadataJSON sql.NullString
		var createdAt time.Time
		if err := relRows.Scan(&id, &userID, &sourceID, &targetID, &relType, &weight, &metadataJSON, &createdAt); err != nil {
			return state, fmt.Errorf("scan relation: %w", err)
		}
		rel := kernel.Relation{ID: id, UserID: userID, SourceID: sourceID, TargetID: targetID, RelationType: relType, Weight: weight, CreatedAt: createdAt.UTC()}
		if metadataJSON.Valid && metadataJSON.String != "" {
			_ = json.Unmarshal([]byte(metadataJSON.String), &rel.Metadata)
		}
		state.Relations = append(state.Relations, rel)
	}

	return state, nil
}

func (s *MySQLStore) UpsertMemory(ctx context.Context, memory kernel.Memory) error {
	embeddingJSON, _ := json.Marshal(memory.Embedding)
	metadataJSON, _ := json.Marshal(memory.Metadata)
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO memories (
			id, user_id, text, context, file_context, session_id, trace_id, category, source_type, status,
			branch_name, confidence, embedding_json, metadata_json, created_at, updated_at
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		ON DUPLICATE KEY UPDATE
			user_id = VALUES(user_id),
			text = VALUES(text),
			context = VALUES(context),
			file_context = VALUES(file_context),
			session_id = VALUES(session_id),
			trace_id = VALUES(trace_id),
			category = VALUES(category),
			source_type = VALUES(source_type),
			status = VALUES(status),
			branch_name = VALUES(branch_name),
			confidence = VALUES(confidence),
			embedding_json = VALUES(embedding_json),
			metadata_json = VALUES(metadata_json),
			created_at = VALUES(created_at),
			updated_at = VALUES(updated_at)
	`, memory.ID, memory.UserID, memory.Text, nullIfEmpty(memory.Context), nullIfEmpty(memory.FileContext), nullIfEmpty(memory.SessionID), nullIfEmpty(memory.TraceID), nullIfEmpty(memory.Category), nullIfEmpty(memory.SourceType), memory.Status, memory.BranchName, memory.Confidence, nullIfJSONEmpty(embeddingJSON), nullIfJSONEmpty(metadataJSON), normalizeTime(memory.CreatedAt), normalizeTime(memory.UpdatedAt))
	if err != nil {
		return fmt.Errorf("upsert memory: %w", err)
	}
	return nil
}

func (s *MySQLStore) UpsertBranch(ctx context.Context, branch kernel.Branch) error {
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO branches (user_id, name, parent, description, status, created_at, updated_at)
		VALUES (?, ?, ?, ?, ?, ?, ?)
		ON DUPLICATE KEY UPDATE
			user_id = VALUES(user_id),
			parent = VALUES(parent),
			description = VALUES(description),
			status = VALUES(status),
			created_at = VALUES(created_at),
			updated_at = VALUES(updated_at)
	`, branch.UserID, branch.Name, nullIfEmpty(branch.Parent), nullIfEmpty(branch.Description), branch.Status, normalizeTime(branch.CreatedAt), normalizeTime(branch.UpdatedAt))
	if err != nil {
		return fmt.Errorf("upsert branch: %w", err)
	}
	return nil
}

func (s *MySQLStore) DeleteBranch(ctx context.Context, userID, branchName string) error {
	_, err := s.db.ExecContext(ctx, `DELETE FROM branches WHERE user_id = ? AND name = ?`, userID, branchName)
	if err != nil {
		return fmt.Errorf("delete branch: %w", err)
	}
	return nil
}

func (s *MySQLStore) UpsertSnapshot(ctx context.Context, snapshot kernel.Snapshot) error {
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO snapshots (id, user_id, branch_name, label, created_at)
		VALUES (?, ?, ?, ?, ?)
		ON DUPLICATE KEY UPDATE
			user_id = VALUES(user_id),
			branch_name = VALUES(branch_name),
			label = VALUES(label),
			created_at = VALUES(created_at)
	`, snapshot.ID, snapshot.UserID, snapshot.Branch, nullIfEmpty(snapshot.Label), normalizeTime(snapshot.CreatedAt))
	if err != nil {
		return fmt.Errorf("upsert snapshot: %w", err)
	}
	return nil
}

func (s *MySQLStore) UpsertRelation(ctx context.Context, relation kernel.Relation) error {
	metadataJSON, _ := json.Marshal(relation.Metadata)
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO memory_relations (id, user_id, source_id, target_id, relation_type, weight, metadata_json, created_at)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?)
		ON DUPLICATE KEY UPDATE
			user_id = VALUES(user_id),
			source_id = VALUES(source_id),
			target_id = VALUES(target_id),
			relation_type = VALUES(relation_type),
			weight = VALUES(weight),
			metadata_json = VALUES(metadata_json),
			created_at = VALUES(created_at)
	`, relation.ID, relation.UserID, relation.SourceID, relation.TargetID, relation.RelationType, relation.Weight, nullIfJSONEmpty(metadataJSON), normalizeTime(relation.CreatedAt))
	if err != nil {
		return fmt.Errorf("upsert relation: %w", err)
	}
	return nil
}

func (s *MySQLStore) DeleteRelation(ctx context.Context, relationID string) error {
	_, err := s.db.ExecContext(ctx, `DELETE FROM memory_relations WHERE id = ?`, relationID)
	if err != nil {
		return fmt.Errorf("delete relation: %w", err)
	}
	return nil
}

func (s *MySQLStore) EnsureMetaSchema(ctx context.Context) error {
	stmts := []string{
		`CREATE TABLE IF NOT EXISTS sessions (
			id VARCHAR(200) PRIMARY KEY,
			user_id VARCHAR(200) NOT NULL DEFAULT '',
			branch_name VARCHAR(100) NOT NULL,
			status VARCHAR(20) NOT NULL,
			started_at DATETIME(6) NOT NULL,
			ended_at DATETIME(6) NULL,
			memory_count INT NOT NULL DEFAULT 0,
			trace_count INT NOT NULL DEFAULT 0,
			hook_count INT NOT NULL DEFAULT 0,
			INDEX idx_session_user (user_id),
			INDEX idx_session_status (status),
			INDEX idx_session_branch (branch_name),
			INDEX idx_session_started (started_at)
		)`,
		`CREATE TABLE IF NOT EXISTS hook_logs (
			seq BIGINT AUTO_INCREMENT PRIMARY KEY,
			event VARCHAR(100) NOT NULL,
			user_id VARCHAR(200) NOT NULL DEFAULT '',
			session_id VARCHAR(200) NULL,
			payload_json LONGTEXT NULL,
			created_at DATETIME(6) NOT NULL,
			INDEX idx_hooklog_user (user_id),
			INDEX idx_hooklog_session (session_id),
			INDEX idx_hooklog_event (event)
		)`,
		`CREATE TABLE IF NOT EXISTS traces (
			id VARCHAR(36) PRIMARY KEY,
			user_id VARCHAR(200) NOT NULL DEFAULT '',
			session_id VARCHAR(200) NULL,
			branch_name VARCHAR(100) NOT NULL,
			trace_type VARCHAR(50) NOT NULL,
			parent_trace_id VARCHAR(36) NULL,
			skill_id VARCHAR(36) NULL,
			task_description TEXT NULL,
			steps_json LONGTEXT NOT NULL,
			metadata_json LONGTEXT NULL,
			created_at DATETIME(6) NOT NULL,
			INDEX idx_trace_user (user_id),
			INDEX idx_trace_session (session_id),
			INDEX idx_trace_branch (branch_name),
			INDEX idx_trace_type (trace_type),
			INDEX idx_trace_parent (parent_trace_id),
			INDEX idx_trace_skill (skill_id)
		)`,
		`CREATE TABLE IF NOT EXISTS trace_comparisons (
			id VARCHAR(36) PRIMARY KEY,
			user_id VARCHAR(200) NOT NULL DEFAULT '',
			trace_a_id VARCHAR(36) NOT NULL,
			trace_b_id VARCHAR(36) NOT NULL,
			skill_id VARCHAR(36) NULL,
			dimension_scores_json LONGTEXT NOT NULL,
			verdict VARCHAR(20) NOT NULL,
			insights_json LONGTEXT NULL,
			created_at DATETIME(6) NOT NULL,
			INDEX idx_comp_user (user_id),
			INDEX idx_comp_trace_a (trace_a_id),
			INDEX idx_comp_trace_b (trace_b_id),
			INDEX idx_comp_skill (skill_id),
			INDEX idx_comp_verdict (verdict)
		)`,
		`CREATE TABLE IF NOT EXISTS api_keys (
			id VARCHAR(36) PRIMARY KEY,
			key_prefix VARCHAR(24) NOT NULL,
			key_hash VARCHAR(128) NOT NULL,
			user_id VARCHAR(200) NOT NULL,
			label VARCHAR(200) NULL,
			scopes_json LONGTEXT NULL,
			created_at DATETIME(6) NOT NULL,
			last_used_at DATETIME(6) NULL,
			revoked_at DATETIME(6) NULL,
			UNIQUE KEY uniq_api_key_prefix (key_prefix),
			INDEX idx_api_keys_user (user_id),
			INDEX idx_api_keys_revoked (revoked_at)
		)`,
	}
	for _, stmt := range stmts {
		if _, err := s.db.ExecContext(ctx, stmt); err != nil {
			return fmt.Errorf("ensure metadata schema: %w", err)
		}
	}
	alterStmts := []string{
		"ALTER TABLE sessions ADD COLUMN user_id VARCHAR(200) NOT NULL DEFAULT ''",
		"ALTER TABLE hook_logs ADD COLUMN user_id VARCHAR(200) NOT NULL DEFAULT ''",
		"ALTER TABLE traces ADD COLUMN user_id VARCHAR(200) NOT NULL DEFAULT ''",
		"ALTER TABLE trace_comparisons ADD COLUMN user_id VARCHAR(200) NOT NULL DEFAULT ''",
		"CREATE INDEX idx_session_user ON sessions (user_id)",
		"CREATE INDEX idx_hooklog_user ON hook_logs (user_id)",
		"CREATE INDEX idx_trace_user ON traces (user_id)",
		"CREATE INDEX idx_comp_user ON trace_comparisons (user_id)",
	}
	for _, stmt := range alterStmts {
		if _, err := s.db.ExecContext(ctx, stmt); err != nil && !isDuplicateDDL(err) {
			return fmt.Errorf("ensure metadata migration: %w", err)
		}
	}
	return nil
}

func (s *MySQLStore) LoadMetaState(ctx context.Context) (meta.PersistedState, error) {
	state := meta.PersistedState{
		Sessions:    []meta.Session{},
		HookLogs:    []meta.HookLog{},
		Traces:      []meta.Trace{},
		Comparisons: []meta.Comparison{},
	}

	sessionRows, err := s.db.QueryContext(ctx, `
		SELECT id, user_id, branch_name, status, started_at, ended_at, memory_count, trace_count, hook_count
		FROM sessions`)
	if err != nil {
		return state, fmt.Errorf("load sessions: %w", err)
	}
	defer sessionRows.Close()
	for sessionRows.Next() {
		var (
			id, userID, branchName, status     string
			startedAt                          time.Time
			endedAt                            sql.NullTime
			memoryCount, traceCount, hookCount int
		)
		if err := sessionRows.Scan(&id, &userID, &branchName, &status, &startedAt, &endedAt, &memoryCount, &traceCount, &hookCount); err != nil {
			return state, fmt.Errorf("scan session: %w", err)
		}
		session := meta.Session{
			ID:          id,
			UserID:      userID,
			BranchName:  branchName,
			Status:      status,
			StartedAt:   startedAt.UTC(),
			MemoryCount: memoryCount,
			TraceCount:  traceCount,
			HookCount:   hookCount,
		}
		if endedAt.Valid {
			ended := endedAt.Time.UTC()
			session.EndedAt = &ended
		}
		state.Sessions = append(state.Sessions, session)
	}

	hookRows, err := s.db.QueryContext(ctx, `
		SELECT seq, event, user_id, session_id, payload_json, created_at
		FROM hook_logs
		ORDER BY seq ASC`)
	if err != nil {
		return state, fmt.Errorf("load hook logs: %w", err)
	}
	defer hookRows.Close()
	for hookRows.Next() {
		var (
			seq         int64
			event       string
			userID      string
			sessionID   sql.NullString
			payloadJSON sql.NullString
			createdAt   time.Time
		)
		if err := hookRows.Scan(&seq, &event, &userID, &sessionID, &payloadJSON, &createdAt); err != nil {
			return state, fmt.Errorf("scan hook log: %w", err)
		}
		hook := meta.HookLog{
			Seq:       seq,
			Event:     event,
			UserID:    userID,
			SessionID: sessionID.String,
			Payload:   map[string]any{},
			CreatedAt: createdAt.UTC(),
		}
		if payloadJSON.Valid && payloadJSON.String != "" {
			_ = json.Unmarshal([]byte(payloadJSON.String), &hook.Payload)
		}
		state.HookLogs = append(state.HookLogs, hook)
	}

	traceRows, err := s.db.QueryContext(ctx, `
		SELECT id, user_id, session_id, branch_name, trace_type, parent_trace_id, skill_id, task_description, steps_json, metadata_json, created_at
		FROM traces`)
	if err != nil {
		return state, fmt.Errorf("load traces: %w", err)
	}
	defer traceRows.Close()
	for traceRows.Next() {
		var (
			id, userID, branchName, traceType                  string
			sessionID, parentTraceID, skillID, taskDescription sql.NullString
			stepsJSON                                          string
			metadataJSON                                       sql.NullString
			createdAt                                          time.Time
		)
		if err := traceRows.Scan(&id, &userID, &sessionID, &branchName, &traceType, &parentTraceID, &skillID, &taskDescription, &stepsJSON, &metadataJSON, &createdAt); err != nil {
			return state, fmt.Errorf("scan trace: %w", err)
		}
		trace := meta.Trace{
			ID:              id,
			UserID:          userID,
			SessionID:       sessionID.String,
			BranchName:      branchName,
			TraceType:       traceType,
			ParentTraceID:   parentTraceID.String,
			SkillID:         skillID.String,
			TaskDescription: taskDescription.String,
			Steps:           []map[string]any{},
			Metadata:        map[string]any{},
			CreatedAt:       createdAt.UTC(),
		}
		_ = json.Unmarshal([]byte(stepsJSON), &trace.Steps)
		if metadataJSON.Valid && metadataJSON.String != "" {
			_ = json.Unmarshal([]byte(metadataJSON.String), &trace.Metadata)
		}
		state.Traces = append(state.Traces, trace)
	}

	comparisonRows, err := s.db.QueryContext(ctx, `
		SELECT id, user_id, trace_a_id, trace_b_id, skill_id, dimension_scores_json, verdict, insights_json, created_at
		FROM trace_comparisons`)
	if err != nil {
		return state, fmt.Errorf("load comparisons: %w", err)
	}
	defer comparisonRows.Close()
	for comparisonRows.Next() {
		var (
			id, userID, traceAID, traceBID, verdict string
			skillID                                 sql.NullString
			dimensionJSON                           string
			insightsJSON                            sql.NullString
			createdAt                               time.Time
		)
		if err := comparisonRows.Scan(&id, &userID, &traceAID, &traceBID, &skillID, &dimensionJSON, &verdict, &insightsJSON, &createdAt); err != nil {
			return state, fmt.Errorf("scan comparison: %w", err)
		}
		comparison := meta.Comparison{
			ID:              id,
			UserID:          userID,
			TraceAID:        traceAID,
			TraceBID:        traceBID,
			SkillID:         skillID.String,
			DimensionScores: map[string]float64{},
			Verdict:         verdict,
			Insights:        map[string]any{},
			CreatedAt:       createdAt.UTC(),
		}
		_ = json.Unmarshal([]byte(dimensionJSON), &comparison.DimensionScores)
		if insightsJSON.Valid && insightsJSON.String != "" {
			_ = json.Unmarshal([]byte(insightsJSON.String), &comparison.Insights)
		}
		state.Comparisons = append(state.Comparisons, comparison)
	}

	return state, nil
}

func (s *MySQLStore) UpsertSession(ctx context.Context, session meta.Session) error {
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO sessions (id, user_id, branch_name, status, started_at, ended_at, memory_count, trace_count, hook_count)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
		ON DUPLICATE KEY UPDATE
			user_id = VALUES(user_id),
			branch_name = VALUES(branch_name),
			status = VALUES(status),
			started_at = VALUES(started_at),
			ended_at = VALUES(ended_at),
			memory_count = VALUES(memory_count),
			trace_count = VALUES(trace_count),
			hook_count = VALUES(hook_count)
	`, session.ID, session.UserID, defaultIfEmpty(session.BranchName, "main"), defaultIfEmpty(session.Status, "active"), normalizeTime(session.StartedAt), session.EndedAt, session.MemoryCount, session.TraceCount, session.HookCount)
	if err != nil {
		return fmt.Errorf("upsert session: %w", err)
	}
	return nil
}

func (s *MySQLStore) InsertHookLog(ctx context.Context, hook meta.HookLog) (int64, error) {
	payloadJSON, _ := json.Marshal(hook.Payload)
	result, err := s.db.ExecContext(ctx, `
		INSERT INTO hook_logs (event, user_id, session_id, payload_json, created_at)
		VALUES (?, ?, ?, ?, ?)
	`, hook.Event, hook.UserID, nullIfEmpty(hook.SessionID), nullIfJSONEmpty(payloadJSON), normalizeTime(hook.CreatedAt))
	if err != nil {
		return 0, fmt.Errorf("insert hook log: %w", err)
	}
	seq, err := result.LastInsertId()
	if err != nil {
		return 0, fmt.Errorf("hook log seq: %w", err)
	}
	return seq, nil
}

func (s *MySQLStore) UpsertTrace(ctx context.Context, trace meta.Trace) error {
	stepsJSON, _ := json.Marshal(trace.Steps)
	metadataJSON, _ := json.Marshal(trace.Metadata)
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO traces (
			id, user_id, session_id, branch_name, trace_type, parent_trace_id, skill_id, task_description, steps_json, metadata_json, created_at
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
		ON DUPLICATE KEY UPDATE
			user_id = VALUES(user_id),
			session_id = VALUES(session_id),
			branch_name = VALUES(branch_name),
			trace_type = VALUES(trace_type),
			parent_trace_id = VALUES(parent_trace_id),
			skill_id = VALUES(skill_id),
			task_description = VALUES(task_description),
			steps_json = VALUES(steps_json),
			metadata_json = VALUES(metadata_json),
			created_at = VALUES(created_at)
	`, trace.ID, trace.UserID, nullIfEmpty(trace.SessionID), defaultIfEmpty(trace.BranchName, "main"), defaultIfEmpty(trace.TraceType, "replay"), nullIfEmpty(trace.ParentTraceID), nullIfEmpty(trace.SkillID), nullIfEmpty(trace.TaskDescription), string(stepsJSON), nullIfJSONEmpty(metadataJSON), normalizeTime(trace.CreatedAt))
	if err != nil {
		return fmt.Errorf("upsert trace: %w", err)
	}
	return nil
}

func (s *MySQLStore) UpsertComparison(ctx context.Context, comparison meta.Comparison) error {
	scoreJSON, _ := json.Marshal(comparison.DimensionScores)
	insightsJSON, _ := json.Marshal(comparison.Insights)
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO trace_comparisons (
			id, user_id, trace_a_id, trace_b_id, skill_id, dimension_scores_json, verdict, insights_json, created_at
		) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
		ON DUPLICATE KEY UPDATE
			user_id = VALUES(user_id),
			trace_a_id = VALUES(trace_a_id),
			trace_b_id = VALUES(trace_b_id),
			skill_id = VALUES(skill_id),
			dimension_scores_json = VALUES(dimension_scores_json),
			verdict = VALUES(verdict),
			insights_json = VALUES(insights_json),
			created_at = VALUES(created_at)
	`, comparison.ID, comparison.UserID, comparison.TraceAID, comparison.TraceBID, nullIfEmpty(comparison.SkillID), string(scoreJSON), defaultIfEmpty(comparison.Verdict, "different"), nullIfJSONEmpty(insightsJSON), normalizeTime(comparison.CreatedAt))
	if err != nil {
		return fmt.Errorf("upsert comparison: %w", err)
	}
	return nil
}

func (s *MySQLStore) CreateAPIKey(ctx context.Context, apiKey meta.APIKey) error {
	scopesJSON, _ := json.Marshal(apiKey.Scopes)
	_, err := s.db.ExecContext(ctx, `
		INSERT INTO api_keys (id, key_prefix, key_hash, user_id, label, scopes_json, created_at, last_used_at, revoked_at)
		VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
	`, apiKey.ID, apiKey.KeyPrefix, apiKey.KeyHash, apiKey.UserID, nullIfEmpty(apiKey.Label), nullIfJSONEmpty(scopesJSON), normalizeTime(apiKey.CreatedAt), apiKey.LastUsedAt, apiKey.RevokedAt)
	if err != nil {
		return fmt.Errorf("create api key: %w", err)
	}
	return nil
}

func (s *MySQLStore) ListAPIKeys(ctx context.Context, userID string) ([]meta.APIKey, error) {
	rows, err := s.db.QueryContext(ctx, `
		SELECT id, key_prefix, key_hash, user_id, label, scopes_json, created_at, last_used_at, revoked_at
		FROM api_keys
		WHERE user_id = ?
		ORDER BY created_at DESC
	`, userID)
	if err != nil {
		return nil, fmt.Errorf("list api keys: %w", err)
	}
	defer rows.Close()

	keys := make([]meta.APIKey, 0)
	for rows.Next() {
		var (
			key                   meta.APIKey
			label, scopesJSON     sql.NullString
			lastUsedAt, revokedAt sql.NullTime
		)
		if err := rows.Scan(&key.ID, &key.KeyPrefix, &key.KeyHash, &key.UserID, &label, &scopesJSON, &key.CreatedAt, &lastUsedAt, &revokedAt); err != nil {
			return nil, fmt.Errorf("scan api key: %w", err)
		}
		key.Label = label.String
		if scopesJSON.Valid && scopesJSON.String != "" {
			_ = json.Unmarshal([]byte(scopesJSON.String), &key.Scopes)
		}
		if lastUsedAt.Valid {
			t := lastUsedAt.Time.UTC()
			key.LastUsedAt = &t
		}
		if revokedAt.Valid {
			t := revokedAt.Time.UTC()
			key.RevokedAt = &t
		}
		key.CreatedAt = key.CreatedAt.UTC()
		keys = append(keys, key)
	}
	return keys, nil
}

func (s *MySQLStore) GetAPIKeyByPrefix(ctx context.Context, keyPrefix string) (*meta.APIKey, error) {
	row := s.db.QueryRowContext(ctx, `
		SELECT id, key_prefix, key_hash, user_id, label, scopes_json, created_at, last_used_at, revoked_at
		FROM api_keys
		WHERE key_prefix = ?
	`, keyPrefix)
	var (
		key                   meta.APIKey
		label, scopesJSON     sql.NullString
		lastUsedAt, revokedAt sql.NullTime
	)
	if err := row.Scan(&key.ID, &key.KeyPrefix, &key.KeyHash, &key.UserID, &label, &scopesJSON, &key.CreatedAt, &lastUsedAt, &revokedAt); err != nil {
		if errors.Is(err, sql.ErrNoRows) {
			return nil, nil
		}
		return nil, fmt.Errorf("get api key by prefix: %w", err)
	}
	key.Label = label.String
	if scopesJSON.Valid && scopesJSON.String != "" {
		_ = json.Unmarshal([]byte(scopesJSON.String), &key.Scopes)
	}
	if lastUsedAt.Valid {
		t := lastUsedAt.Time.UTC()
		key.LastUsedAt = &t
	}
	if revokedAt.Valid {
		t := revokedAt.Time.UTC()
		key.RevokedAt = &t
	}
	key.CreatedAt = key.CreatedAt.UTC()
	return &key, nil
}

func (s *MySQLStore) RevokeAPIKey(ctx context.Context, keyID string, revokedAt time.Time) error {
	_, err := s.db.ExecContext(ctx, `UPDATE api_keys SET revoked_at = ? WHERE id = ?`, normalizeTime(revokedAt), keyID)
	if err != nil {
		return fmt.Errorf("revoke api key: %w", err)
	}
	return nil
}

func (s *MySQLStore) TouchAPIKeyLastUsed(ctx context.Context, keyID string, usedAt time.Time) error {
	_, err := s.db.ExecContext(ctx, `UPDATE api_keys SET last_used_at = ? WHERE id = ?`, normalizeTime(usedAt), keyID)
	if err != nil {
		return fmt.Errorf("touch api key: %w", err)
	}
	return nil
}

func (s *MySQLStore) AssignLegacyDataToUser(ctx context.Context, userID string) error {
	trimmed := strings.TrimSpace(userID)
	if trimmed == "" {
		return nil
	}
	stmts := []struct {
		query string
		args  []any
	}{
		{query: "UPDATE memories SET user_id = ? WHERE user_id = '' OR user_id IS NULL", args: []any{trimmed}},
		{query: "UPDATE branches SET user_id = ? WHERE user_id = '' OR user_id IS NULL", args: []any{trimmed}},
		{query: "UPDATE snapshots SET user_id = ? WHERE user_id = '' OR user_id IS NULL", args: []any{trimmed}},
		{query: "UPDATE memory_relations SET user_id = ? WHERE user_id = '' OR user_id IS NULL", args: []any{trimmed}},
		{query: "UPDATE sessions SET user_id = ? WHERE user_id = '' OR user_id IS NULL", args: []any{trimmed}},
		{query: "UPDATE hook_logs SET user_id = ? WHERE user_id = '' OR user_id IS NULL", args: []any{trimmed}},
		{query: "UPDATE traces SET user_id = ? WHERE user_id = '' OR user_id IS NULL", args: []any{trimmed}},
		{query: "UPDATE trace_comparisons SET user_id = ? WHERE user_id = '' OR user_id IS NULL", args: []any{trimmed}},
	}
	for _, stmt := range stmts {
		if _, err := s.db.ExecContext(ctx, stmt.query, stmt.args...); err != nil {
			return fmt.Errorf("assign legacy data: %w", err)
		}
	}
	return nil
}

func normalizeTime(t time.Time) time.Time {
	if t.IsZero() {
		return time.Now().UTC()
	}
	return t.UTC()
}

func nullIfEmpty(v string) any {
	if v == "" {
		return nil
	}
	return v
}

func nullIfJSONEmpty(v []byte) any {
	if len(v) == 0 || string(v) == "null" || string(v) == "[]" || string(v) == "{}" {
		return nil
	}
	return string(v)
}

func defaultIfEmpty(v, fallback string) string {
	if v == "" {
		return fallback
	}
	return v
}

func isDuplicateDDL(err error) bool {
	if err == nil {
		return false
	}
	msg := strings.ToLower(err.Error())
	return strings.Contains(msg, "duplicate column") ||
		strings.Contains(msg, "duplicate key name") ||
		strings.Contains(msg, "already exists")
}
