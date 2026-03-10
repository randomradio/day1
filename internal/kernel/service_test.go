package kernel

import (
	"context"
	"testing"
	"time"
)

type testEmbedder struct{}

func (t *testEmbedder) Embed(_ context.Context, text string) ([]float32, error) {
	out := make([]float32, 32)
	for i := range out {
		out[i] = float32(len(text)+i) / 100.0
	}
	return out, nil
}

func (t *testEmbedder) EmbedBatch(ctx context.Context, texts []string) ([][]float32, error) {
	out := make([][]float32, 0, len(texts))
	for _, text := range texts {
		vec, err := t.Embed(ctx, text)
		if err != nil {
			return nil, err
		}
		out = append(out, vec)
	}
	return out, nil
}

type testLLM struct{}

func (t *testLLM) Complete(_ context.Context, _ string) (string, error) {
	return "", nil
}

func newKernel() *MemoryService {
	return NewMemoryService(&testEmbedder{}, &testLLM{})
}

func TestWriteAndGet(t *testing.T) {
	svc := newKernel()
	ctx := context.Background()

	memory, err := svc.Write(ctx, WriteRequest{Text: "Test memory", SessionID: "s1"})
	if err != nil {
		t.Fatalf("write failed: %v", err)
	}
	if memory.ID == "" {
		t.Fatalf("expected memory id")
	}
	if memory.BranchName != "main" {
		t.Fatalf("expected main branch, got %s", memory.BranchName)
	}

	got, err := svc.Get(ctx, memory.ID)
	if err != nil {
		t.Fatalf("get failed: %v", err)
	}
	if got.Text != "Test memory" {
		t.Fatalf("unexpected text: %s", got.Text)
	}
}

func TestSearchBranchIsolation(t *testing.T) {
	svc := newKernel()
	ctx := context.Background()
	if _, err := svc.CreateBranch(ctx, "feature", "main", ""); err != nil {
		t.Fatalf("create branch failed: %v", err)
	}
	if _, err := svc.Write(ctx, WriteRequest{Text: "Main branch memory", BranchName: "main"}); err != nil {
		t.Fatalf("write main failed: %v", err)
	}
	if _, err := svc.Write(ctx, WriteRequest{Text: "Feature branch memory", BranchName: "feature"}); err != nil {
		t.Fatalf("write feature failed: %v", err)
	}

	mainResults, err := svc.Search(ctx, SearchRequest{Query: "memory", BranchName: "main"})
	if err != nil {
		t.Fatalf("search main failed: %v", err)
	}
	for _, result := range mainResults {
		if result.BranchName != "main" {
			t.Fatalf("unexpected branch in main results: %s", result.BranchName)
		}
	}
}

func TestArchiveExcludedFromCountAndSearch(t *testing.T) {
	svc := newKernel()
	ctx := context.Background()
	m1, err := svc.Write(ctx, WriteRequest{Text: "Active memory"})
	if err != nil {
		t.Fatalf("write active failed: %v", err)
	}
	m2, err := svc.Write(ctx, WriteRequest{Text: "Archived memory"})
	if err != nil {
		t.Fatalf("write archived failed: %v", err)
	}
	if _, err := svc.Archive(ctx, m2.ID); err != nil {
		t.Fatalf("archive failed: %v", err)
	}

	count, err := svc.Count(ctx, "main", false)
	if err != nil {
		t.Fatalf("count failed: %v", err)
	}
	if count != 1 {
		t.Fatalf("expected count=1, got %d", count)
	}

	results, err := svc.Search(ctx, SearchRequest{Query: "memory", BranchName: "main"})
	if err != nil {
		t.Fatalf("search failed: %v", err)
	}
	for _, result := range results {
		if result.ID == m2.ID {
			t.Fatalf("archived memory should not appear in results")
		}
	}

	if m1.ID == "" {
		t.Fatalf("sanity check failed")
	}
}

func TestSnapshotRestoreArchivesNewerMemories(t *testing.T) {
	svc := newKernel()
	ctx := context.Background()
	if _, err := svc.Write(ctx, WriteRequest{Text: "before snapshot"}); err != nil {
		t.Fatalf("write before snapshot failed: %v", err)
	}
	snapshot, err := svc.Snapshot(ctx, "main", "baseline")
	if err != nil {
		t.Fatalf("snapshot failed: %v", err)
	}
	time.Sleep(time.Millisecond)
	newer, err := svc.Write(ctx, WriteRequest{Text: "after snapshot"})
	if err != nil {
		t.Fatalf("write after snapshot failed: %v", err)
	}

	archived, err := svc.Restore(ctx, snapshot.ID)
	if err != nil {
		t.Fatalf("restore failed: %v", err)
	}
	if archived != 1 {
		t.Fatalf("expected archived=1, got %d", archived)
	}

	got, err := svc.Get(ctx, newer.ID)
	if err != nil {
		t.Fatalf("get newer failed: %v", err)
	}
	if got.Status != "archived" {
		t.Fatalf("expected archived status, got %s", got.Status)
	}
}

func TestMergeDeduplicatesByText(t *testing.T) {
	svc := newKernel()
	ctx := context.Background()
	if _, err := svc.CreateBranch(ctx, "feature", "main", ""); err != nil {
		t.Fatalf("create branch failed: %v", err)
	}
	if _, err := svc.Write(ctx, WriteRequest{Text: "shared", BranchName: "main"}); err != nil {
		t.Fatalf("write main failed: %v", err)
	}
	if _, err := svc.Write(ctx, WriteRequest{Text: "shared", BranchName: "feature"}); err != nil {
		t.Fatalf("write feature shared failed: %v", err)
	}
	if _, err := svc.Write(ctx, WriteRequest{Text: "feature only", BranchName: "feature"}); err != nil {
		t.Fatalf("write feature unique failed: %v", err)
	}

	result, err := svc.Merge(ctx, "feature", "main")
	if err != nil {
		t.Fatalf("merge failed: %v", err)
	}
	if result.Merged != 1 || result.Skipped != 1 {
		t.Fatalf("unexpected merge result: %+v", result)
	}
}

func TestGraphTraversal(t *testing.T) {
	svc := newKernel()
	ctx := context.Background()
	m1, _ := svc.Write(ctx, WriteRequest{Text: "Root"})
	m2, _ := svc.Write(ctx, WriteRequest{Text: "Child"})
	m3, _ := svc.Write(ctx, WriteRequest{Text: "Grandchild"})
	if _, err := svc.Relate(ctx, m1.ID, m2.ID, "depends_on", 1, nil); err != nil {
		t.Fatalf("relate m1->m2 failed: %v", err)
	}
	if _, err := svc.Relate(ctx, m2.ID, m3.ID, "depends_on", 1, nil); err != nil {
		t.Fatalf("relate m2->m3 failed: %v", err)
	}

	graph, err := svc.Graph(ctx, m1.ID, 2, 10)
	if err != nil {
		t.Fatalf("graph failed: %v", err)
	}
	if len(graph.Nodes) < 3 {
		t.Fatalf("expected >=3 nodes, got %d", len(graph.Nodes))
	}
	if len(graph.Edges) < 2 {
		t.Fatalf("expected >=2 edges, got %d", len(graph.Edges))
	}
}

func TestUserIsolationByContext(t *testing.T) {
	svc := newKernel()
	ctxA := WithUserID(context.Background(), "user-a")
	ctxB := WithUserID(context.Background(), "user-b")

	memA, err := svc.Write(ctxA, WriteRequest{Text: "A private memory"})
	if err != nil {
		t.Fatalf("write A failed: %v", err)
	}
	if _, err := svc.Write(ctxB, WriteRequest{Text: "B private memory"}); err != nil {
		t.Fatalf("write B failed: %v", err)
	}

	countA, err := svc.Count(ctxA, "main", false)
	if err != nil {
		t.Fatalf("count A failed: %v", err)
	}
	if countA != 1 {
		t.Fatalf("expected user-a count=1, got %d", countA)
	}

	countB, err := svc.Count(ctxB, "main", false)
	if err != nil {
		t.Fatalf("count B failed: %v", err)
	}
	if countB != 1 {
		t.Fatalf("expected user-b count=1, got %d", countB)
	}

	if _, err := svc.Get(ctxB, memA.ID); err == nil {
		t.Fatalf("expected not found when user-b reads user-a memory")
	}
}
