package mcp

import (
	"context"
	"fmt"
	"sort"
	"strings"

	"day1/internal/kernel"
)

type Handler func(context.Context, map[string]any) (any, error)

type Tool struct {
	Name        string         `json:"name"`
	Description string         `json:"description"`
	InputSchema map[string]any `json:"input_schema"`
}

type registeredTool struct {
	tool    Tool
	handler Handler
}

type Registry struct {
	kernel kernel.MemoryKernel
	tools  map[string]registeredTool
}

func NewRegistry(k kernel.MemoryKernel) *Registry {
	r := &Registry{kernel: k, tools: make(map[string]registeredTool)}
	r.registerDefaults()
	return r
}

func (r *Registry) ListTools() []Tool {
	out := make([]Tool, 0, len(r.tools))
	for _, t := range r.tools {
		out = append(out, t.tool)
	}
	sort.Slice(out, func(i, j int) bool {
		return out[i].Name < out[j].Name
	})
	return out
}

func (r *Registry) CallTool(ctx context.Context, name string, args map[string]any) (any, error) {
	entry, ok := r.tools[name]
	if !ok {
		return nil, fmt.Errorf("unknown tool: %s", name)
	}
	if args == nil {
		args = map[string]any{}
	}
	return entry.handler(ctx, args)
}

func (r *Registry) register(name, description string, schema map[string]any, handler Handler) {
	r.tools[name] = registeredTool{
		tool:    Tool{Name: name, Description: description, InputSchema: schema},
		handler: handler,
	}
}

func (r *Registry) registerDefaults() {
	r.register("memory_write", "Store a memory entry.", schemaReq("text"), r.memoryWrite)
	r.register("memory_write_batch", "Store multiple memory entries.", schemaReq("items"), r.memoryWriteBatch)
	r.register("memory_get", "Get memory by ID.", schemaReq("memory_id"), r.memoryGet)
	r.register("memory_update", "Update memory fields.", schemaReq("memory_id"), r.memoryUpdate)
	r.register("memory_archive", "Archive a memory.", schemaReq("memory_id"), r.memoryArchive)
	r.register("memory_archive_batch", "Archive multiple memories.", schemaReq("memory_ids"), r.memoryArchiveBatch)
	r.register("memory_search", "Semantic/text memory search.", schemaReq("query"), r.memorySearch)
	r.register("memory_timeline", "Chronological memory timeline.", map[string]any{"type": "object"}, r.memoryTimeline)
	r.register("memory_count", "Memory count by branch.", map[string]any{"type": "object"}, r.memoryCount)

	r.register("memory_branch_create", "Create branch.", schemaReq("name"), r.branchCreate)
	r.register("memory_branch_switch", "Switch to branch.", schemaReq("name"), r.branchSwitch)
	r.register("memory_branch_list", "List branches.", map[string]any{"type": "object"}, r.branchList)
	r.register("memory_branch_archive", "Archive branch.", schemaReq("name"), r.branchArchive)
	r.register("memory_branch_delete", "Delete branch.", schemaReq("name"), r.branchDelete)

	r.register("memory_snapshot", "Create snapshot.", map[string]any{"type": "object"}, r.snapshotCreate)
	r.register("memory_snapshot_list", "List snapshots.", map[string]any{"type": "object"}, r.snapshotList)
	r.register("memory_restore", "Restore snapshot.", schemaReq("snapshot_id"), r.snapshotRestore)
	r.register("memory_merge", "Merge branches.", schemaReq("source", "target"), r.memoryMerge)

	r.register("memory_relate", "Create relation between memories.", schemaReq("source_id", "target_id"), r.relate)
	r.register("memory_relations", "List relations for a memory.", schemaReq("memory_id"), r.relations)
	r.register("memory_graph", "Traverse memory graph.", schemaReq("memory_id"), r.graph)
	r.register("memory_relation_delete", "Delete relation by ID.", schemaReq("relation_id"), r.relationDelete)
}

func (r *Registry) memoryWrite(ctx context.Context, args map[string]any) (any, error) {
	req := kernel.WriteRequest{
		Text:        getString(args, "text", ""),
		Context:     getString(args, "context", ""),
		FileContext: getString(args, "file_context", ""),
		SessionID:   getString(args, "session_id", ""),
		TraceID:     getString(args, "trace_id", ""),
		Category:    getString(args, "category", ""),
		SourceType:  getString(args, "source_type", ""),
		Status:      getString(args, "status", ""),
		BranchName:  getString(args, "branch", getString(args, "branch_name", "")),
		Confidence:  getFloat(args, "confidence", 0),
	}
	return r.kernel.Write(ctx, req)
}

func (r *Registry) memoryWriteBatch(ctx context.Context, args map[string]any) (any, error) {
	rawItems := getSlice(args, "items")
	items := make([]kernel.WriteRequest, 0, len(rawItems))
	for _, raw := range rawItems {
		m, ok := raw.(map[string]any)
		if !ok {
			continue
		}
		item := kernel.WriteRequest{
			Text:        getString(m, "text", ""),
			Context:     getString(m, "context", ""),
			FileContext: getString(m, "file_context", ""),
			SessionID:   getString(m, "session_id", ""),
			TraceID:     getString(m, "trace_id", ""),
			Category:    getString(m, "category", ""),
			SourceType:  getString(m, "source_type", ""),
			Status:      getString(m, "status", ""),
			BranchName:  getString(args, "branch", getString(m, "branch", "")),
			Confidence:  getFloat(m, "confidence", 0),
		}
		items = append(items, item)
	}
	return r.kernel.WriteBatch(ctx, items)
}

func (r *Registry) memoryGet(ctx context.Context, args map[string]any) (any, error) {
	return r.kernel.Get(ctx, getString(args, "memory_id", ""))
}

func (r *Registry) memoryUpdate(ctx context.Context, args map[string]any) (any, error) {
	req := kernel.UpdateRequest{MemoryID: getString(args, "memory_id", "")}
	if v, ok := getOptString(args, "text"); ok {
		req.Text = &v
	}
	if v, ok := getOptString(args, "context"); ok {
		req.Context = &v
	}
	if v, ok := getOptString(args, "file_context"); ok {
		req.FileContext = &v
	}
	if v, ok := getOptString(args, "category"); ok {
		req.Category = &v
	}
	if v, ok := getOptString(args, "source_type"); ok {
		req.SourceType = &v
	}
	if v, ok := getOptString(args, "status"); ok {
		req.Status = &v
	}
	if v, ok := getOptFloat(args, "confidence"); ok {
		req.Confidence = &v
	}
	if metadata, ok := args["metadata"].(map[string]any); ok {
		req.Metadata = metadata
	}
	return r.kernel.Update(ctx, req)
}

func (r *Registry) memoryArchive(ctx context.Context, args map[string]any) (any, error) {
	return r.kernel.Archive(ctx, getString(args, "memory_id", ""))
}

func (r *Registry) memoryArchiveBatch(ctx context.Context, args map[string]any) (any, error) {
	count, err := r.kernel.ArchiveBatch(ctx, getStringSlice(args, "memory_ids"))
	if err != nil {
		return nil, err
	}
	return map[string]any{"archived": count}, nil
}

func (r *Registry) memorySearch(ctx context.Context, args map[string]any) (any, error) {
	req := kernel.SearchRequest{
		Query:      getString(args, "query", ""),
		BranchName: getString(args, "branch", getString(args, "branch_name", "")),
		Category:   getString(args, "category", ""),
		SourceType: getString(args, "source_type", ""),
		Status:     getString(args, "status", ""),
		SessionID:  getString(args, "session_id", ""),
		Limit:      getInt(args, "limit", 20),
	}
	return r.kernel.Search(ctx, req)
}

func (r *Registry) memoryTimeline(ctx context.Context, args map[string]any) (any, error) {
	req := kernel.TimelineRequest{
		BranchName: getString(args, "branch", getString(args, "branch_name", "")),
		Category:   getString(args, "category", ""),
		SourceType: getString(args, "source_type", ""),
		SessionID:  getString(args, "session_id", ""),
		Limit:      getInt(args, "limit", 20),
	}
	items, err := r.kernel.Timeline(ctx, req)
	if err != nil {
		return nil, err
	}
	return map[string]any{"timeline": items, "count": len(items)}, nil
}

func (r *Registry) memoryCount(ctx context.Context, args map[string]any) (any, error) {
	branch := getString(args, "branch", "main")
	count, err := r.kernel.Count(ctx, branch, false)
	if err != nil {
		return nil, err
	}
	return map[string]any{"branch": branch, "count": count}, nil
}

func (r *Registry) branchCreate(ctx context.Context, args map[string]any) (any, error) {
	return r.kernel.CreateBranch(ctx, getString(args, "name", ""), getString(args, "parent", "main"), getString(args, "description", ""))
}

func (r *Registry) branchSwitch(ctx context.Context, args map[string]any) (any, error) {
	return r.kernel.SwitchBranch(ctx, getString(args, "name", ""))
}

func (r *Registry) branchList(ctx context.Context, _ map[string]any) (any, error) {
	branches, err := r.kernel.ListBranches(ctx)
	if err != nil {
		return nil, err
	}
	return map[string]any{"branches": branches, "count": len(branches)}, nil
}

func (r *Registry) branchArchive(ctx context.Context, args map[string]any) (any, error) {
	return r.kernel.ArchiveBranch(ctx, getString(args, "name", ""))
}

func (r *Registry) branchDelete(ctx context.Context, args map[string]any) (any, error) {
	if err := r.kernel.DeleteBranch(ctx, getString(args, "name", "")); err != nil {
		return nil, err
	}
	return map[string]any{"deleted": true}, nil
}

func (r *Registry) snapshotCreate(ctx context.Context, args map[string]any) (any, error) {
	return r.kernel.Snapshot(ctx, getString(args, "branch", "main"), getString(args, "label", ""))
}

func (r *Registry) snapshotList(ctx context.Context, args map[string]any) (any, error) {
	items, err := r.kernel.ListSnapshots(ctx, getString(args, "branch", "main"))
	if err != nil {
		return nil, err
	}
	return map[string]any{"snapshots": items, "count": len(items)}, nil
}

func (r *Registry) snapshotRestore(ctx context.Context, args map[string]any) (any, error) {
	count, err := r.kernel.Restore(ctx, getString(args, "snapshot_id", ""))
	if err != nil {
		return nil, err
	}
	return map[string]any{"archived": count}, nil
}

func (r *Registry) memoryMerge(ctx context.Context, args map[string]any) (any, error) {
	return r.kernel.Merge(ctx, getString(args, "source", ""), getString(args, "target", "main"))
}

func (r *Registry) relate(ctx context.Context, args map[string]any) (any, error) {
	return r.kernel.Relate(
		ctx,
		getString(args, "source_id", ""),
		getString(args, "target_id", ""),
		getString(args, "relation_type", "related_to"),
		getFloat(args, "weight", 1.0),
		getMap(args, "metadata"),
	)
}

func (r *Registry) relations(ctx context.Context, args map[string]any) (any, error) {
	rels, err := r.kernel.Relations(
		ctx,
		getString(args, "memory_id", ""),
		getString(args, "relation_type", ""),
		getString(args, "direction", "both"),
	)
	if err != nil {
		return nil, err
	}
	return map[string]any{"relations": rels, "count": len(rels)}, nil
}

func (r *Registry) graph(ctx context.Context, args map[string]any) (any, error) {
	return r.kernel.Graph(ctx, getString(args, "memory_id", ""), getInt(args, "depth", 1), getInt(args, "limit", 50))
}

func (r *Registry) relationDelete(ctx context.Context, args map[string]any) (any, error) {
	if err := r.kernel.DeleteRelation(ctx, getString(args, "relation_id", "")); err != nil {
		return nil, err
	}
	return map[string]any{"deleted": true}, nil
}

func schemaReq(required ...string) map[string]any {
	return map[string]any{
		"type":     "object",
		"required": required,
	}
}

func getString(m map[string]any, key, fallback string) string {
	value, ok := m[key]
	if !ok || value == nil {
		return fallback
	}
	s, ok := value.(string)
	if !ok {
		return fallback
	}
	s = strings.TrimSpace(s)
	if s == "" {
		return fallback
	}
	return s
}

func getOptString(m map[string]any, key string) (string, bool) {
	value, ok := m[key]
	if !ok || value == nil {
		return "", false
	}
	s, ok := value.(string)
	if !ok {
		return "", false
	}
	return s, true
}

func getInt(m map[string]any, key string, fallback int) int {
	value, ok := m[key]
	if !ok || value == nil {
		return fallback
	}
	switch v := value.(type) {
	case float64:
		return int(v)
	case int:
		return v
	case int64:
		return int(v)
	default:
		return fallback
	}
}

func getFloat(m map[string]any, key string, fallback float64) float64 {
	value, ok := m[key]
	if !ok || value == nil {
		return fallback
	}
	switch v := value.(type) {
	case float64:
		return v
	case float32:
		return float64(v)
	case int:
		return float64(v)
	case int64:
		return float64(v)
	default:
		return fallback
	}
}

func getOptFloat(m map[string]any, key string) (float64, bool) {
	value, ok := m[key]
	if !ok || value == nil {
		return 0, false
	}
	switch v := value.(type) {
	case float64:
		return v, true
	case float32:
		return float64(v), true
	case int:
		return float64(v), true
	case int64:
		return float64(v), true
	default:
		return 0, false
	}
}

func getMap(m map[string]any, key string) map[string]any {
	value, ok := m[key]
	if !ok || value == nil {
		return nil
	}
	v, ok := value.(map[string]any)
	if !ok {
		return nil
	}
	return v
}

func getSlice(m map[string]any, key string) []any {
	value, ok := m[key]
	if !ok || value == nil {
		return nil
	}
	s, ok := value.([]any)
	if ok {
		return s
	}
	if typed, ok := value.([]map[string]any); ok {
		out := make([]any, 0, len(typed))
		for _, item := range typed {
			out = append(out, item)
		}
		return out
	}
	return nil
}

func getStringSlice(m map[string]any, key string) []string {
	raw := getSlice(m, key)
	out := make([]string, 0, len(raw))
	for _, item := range raw {
		s, ok := item.(string)
		if !ok || strings.TrimSpace(s) == "" {
			continue
		}
		out = append(out, s)
	}
	return out
}
