package main

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"flag"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"strings"
	"time"

	"day1/internal/api"
	"day1/internal/config"
	"day1/internal/kernel"
	"day1/internal/mcp"
	"day1/internal/providers/embedding"
	"day1/internal/providers/llm"
	"day1/internal/storage"
)

func main() {
	if len(os.Args) < 2 {
		printHelp()
		return
	}

	cmd := os.Args[1]
	args := os.Args[2:]
	var err error

	switch cmd {
	case "help", "--help", "-h":
		printHelp()
		return
	case "api":
		err = runAPIServer()
	case "health":
		err = runHealth(args)
	case "write":
		err = runWrite(args)
	case "search":
		err = runSearch(args)
	case "timeline":
		err = runTimeline(args)
	case "count":
		err = runCount(args)
	case "branch":
		err = runBranch(args)
	case "merge":
		err = runMerge(args)
	case "snapshot":
		err = runSnapshot(args)
	case "test":
		err = runTests(args)
	case "migrate":
		err = runMigrate(args)
	case "init":
		err = runInit(args)
	default:
		err = fmt.Errorf("unknown command: %s", cmd)
	}

	if err != nil {
		var exitErr *exec.ExitError
		if errors.As(err, &exitErr) {
			os.Exit(exitErr.ExitCode())
		}
		fmt.Fprintf(os.Stderr, "error: %v\n", err)
		os.Exit(1)
	}
}

func printHelp() {
	fmt.Println("Day1 Go CLI")
	fmt.Println("")
	fmt.Println("Commands:")
	fmt.Println("  help")
	fmt.Println("  test | api | migrate | init | health")
	fmt.Println("  write <text> [--category --confidence --session --branch --context --file-context]")
	fmt.Println("  search <query> [--limit --category --branch]")
	fmt.Println("  timeline [--branch --limit --category --source-type --session]")
	fmt.Println("  count [--branch]")
	fmt.Println("  branch <create|switch|list|archive|delete> ...")
	fmt.Println("  merge <source> [--into target]")
	fmt.Println("  snapshot <create|list|restore> ...")
	fmt.Println("")
	fmt.Println("Environment:")
	fmt.Println("  DAY1_API_URL (default http://127.0.0.1:9821)")
	fmt.Println("  DAY1_API_KEY (optional request key for auth-enabled API)")
}

func runAPIServer() error {
	cfg := config.LoadFromEnv()
	if err := cfg.ValidateBYOK(); err != nil {
		return err
	}

	embedder, err := embedding.NewProvider(cfg)
	if err != nil {
		return err
	}
	llmProvider, err := llm.NewProvider(cfg)
	if err != nil {
		return err
	}

	var memoryKernel kernel.MemoryKernel
	var sqlStore *storage.MySQLStore
	if cfg.DatabaseURL != "" {
		store, err := storage.NewMySQLStoreFromURL(cfg.DatabaseURL)
		if err != nil {
			return err
		}
		sqlStore = store
		defer func() { _ = sqlStore.Close() }()
		if cfg.AuthEnabled {
			ctx := context.Background()
			if err := store.EnsureSchema(ctx); err != nil {
				return err
			}
			if err := store.EnsureMetaSchema(ctx); err != nil {
				return err
			}
			if err := store.AssignLegacyDataToUser(ctx, cfg.BootstrapAdminUserID); err != nil {
				return err
			}
		}
		sqlKernel, err := kernel.NewMemoryServiceWithStore(context.Background(), embedder, llmProvider, store)
		if err != nil {
			return err
		}
		memoryKernel = sqlKernel
	} else {
		memoryKernel = kernel.NewMemoryService(embedder, llmProvider)
	}

	registry := mcp.NewRegistry(memoryKernel)
	var metadataStore api.MetadataStore
	if sqlStore != nil {
		metadataStore = sqlStore
	}
	server, err := api.NewServer(cfg, memoryKernel, registry, metadataStore)
	if err != nil {
		return err
	}

	httpServer := &http.Server{
		Addr:              ":" + strconv(cfg.Port),
		Handler:           server.Router(),
		ReadHeaderTimeout: 10 * time.Second,
		ReadTimeout:       20 * time.Second,
		WriteTimeout:      20 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	return httpServer.ListenAndServe()
}

func runTests(args []string) error {
	cmdArgs := []string{"test", "./..."}
	cmdArgs = append(cmdArgs, args...)
	return runCommand("go", "", cmdArgs...)
}

func runMigrate(_ []string) error {
	cfg := config.LoadFromEnv()
	if strings.TrimSpace(cfg.DatabaseURL) == "" {
		return fmt.Errorf("DAY1_DATABASE_URL is required for migrate")
	}
	store, err := storage.NewMySQLStoreFromURL(cfg.DatabaseURL)
	if err != nil {
		return err
	}
	defer func() { _ = store.Close() }()
	ctx := context.Background()
	if err := store.EnsureSchema(ctx); err != nil {
		return err
	}
	if err := store.EnsureMetaSchema(ctx); err != nil {
		return err
	}
	fmt.Println("migrations complete")
	return nil
}

func runInit(_ []string) error {
	cfg := config.LoadFromEnv()
	if strings.TrimSpace(cfg.DatabaseURL) == "" {
		return fmt.Errorf("DAY1_DATABASE_URL is required for init")
	}
	store, err := storage.NewMySQLStoreFromURL(cfg.DatabaseURL)
	if err != nil {
		return err
	}
	defer func() { _ = store.Close() }()

	ctx := context.Background()
	if err := store.EnsureSchema(ctx); err != nil {
		return err
	}
	if err := store.EnsureMetaSchema(ctx); err != nil {
		return err
	}

	if _, err := kernel.NewMemoryServiceWithStore(ctx, embedding.NewMockProvider(32), &llm.MockProvider{}, store); err != nil {
		return err
	}

	fmt.Println("init complete")
	return nil
}

func runHealth(args []string) error {
	fs := flag.NewFlagSet("health", flag.ContinueOnError)
	if err := fs.Parse(args); err != nil {
		return err
	}
	resp, err := apiRequest(http.MethodGet, "/health", nil, nil)
	if err != nil {
		return err
	}
	printJSON(resp)
	return nil
}

func runWrite(args []string) error {
	fs := flag.NewFlagSet("write", flag.ContinueOnError)
	category := fs.String("category", "", "memory category")
	confidence := fs.Float64("confidence", 0, "confidence")
	sessionID := fs.String("session", "", "session id")
	branch := fs.String("branch", "main", "branch")
	contextText := fs.String("context", "", "context")
	fileContext := fs.String("file-context", "", "file context")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if fs.NArg() < 1 {
		return fmt.Errorf("write requires text")
	}
	payload := map[string]any{
		"text":         fs.Arg(0),
		"category":     *category,
		"confidence":   *confidence,
		"session_id":   *sessionID,
		"branch_name":  *branch,
		"context":      *contextText,
		"file_context": *fileContext,
	}
	resp, err := apiRequest(http.MethodPost, "/api/v1/memories", payload, nil)
	if err != nil {
		return err
	}
	printJSON(resp)
	return nil
}

func runSearch(args []string) error {
	fs := flag.NewFlagSet("search", flag.ContinueOnError)
	limit := fs.Int("limit", 20, "result limit")
	category := fs.String("category", "", "category")
	branch := fs.String("branch", "main", "branch")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if fs.NArg() < 1 {
		return fmt.Errorf("search requires query")
	}
	payload := map[string]any{
		"tool": "memory_search",
		"arguments": map[string]any{
			"query":    fs.Arg(0),
			"limit":    *limit,
			"category": *category,
			"branch":   *branch,
		},
	}
	resp, err := apiRequest(http.MethodPost, "/api/v1/ingest/mcp", payload, nil)
	if err != nil {
		return err
	}
	printJSON(resp)
	return nil
}

func runTimeline(args []string) error {
	fs := flag.NewFlagSet("timeline", flag.ContinueOnError)
	branch := fs.String("branch", "main", "branch")
	limit := fs.Int("limit", 20, "limit")
	category := fs.String("category", "", "category")
	sourceType := fs.String("source-type", "", "source type")
	sessionID := fs.String("session", "", "session id")
	if err := fs.Parse(args); err != nil {
		return err
	}
	query := map[string]string{
		"branch":      *branch,
		"limit":       fmt.Sprintf("%d", *limit),
		"category":    *category,
		"source_type": *sourceType,
		"session_id":  *sessionID,
	}
	resp, err := apiRequest(http.MethodGet, "/api/v1/memories/timeline", nil, query)
	if err != nil {
		return err
	}
	printJSON(resp)
	return nil
}

func runCount(args []string) error {
	fs := flag.NewFlagSet("count", flag.ContinueOnError)
	branch := fs.String("branch", "main", "branch")
	if err := fs.Parse(args); err != nil {
		return err
	}
	resp, err := apiRequest(http.MethodGet, "/api/v1/memories/count", nil, map[string]string{"branch": *branch})
	if err != nil {
		return err
	}
	printJSON(resp)
	return nil
}

func runBranch(args []string) error {
	if len(args) == 0 {
		return fmt.Errorf("branch requires subcommand")
	}
	sub := args[0]
	subArgs := args[1:]
	fs := flag.NewFlagSet("branch", flag.ContinueOnError)
	parent := fs.String("parent", "main", "parent branch")
	description := fs.String("description", "", "description")
	if err := fs.Parse(subArgs); err != nil {
		return err
	}

	var payload map[string]any
	switch sub {
	case "list":
		payload = map[string]any{"tool": "memory_branch_list", "arguments": map[string]any{}}
	case "create":
		if fs.NArg() < 1 {
			return fmt.Errorf("branch create requires name")
		}
		payload = map[string]any{
			"tool": "memory_branch_create",
			"arguments": map[string]any{
				"name":        fs.Arg(0),
				"parent":      *parent,
				"description": *description,
			},
		}
	case "switch", "archive", "delete":
		if fs.NArg() < 1 {
			return fmt.Errorf("branch %s requires name", sub)
		}
		tool := map[string]string{"switch": "memory_branch_switch", "archive": "memory_branch_archive", "delete": "memory_branch_delete"}[sub]
		payload = map[string]any{"tool": tool, "arguments": map[string]any{"name": fs.Arg(0)}}
	default:
		return fmt.Errorf("unsupported branch subcommand: %s", sub)
	}

	resp, err := apiRequest(http.MethodPost, "/api/v1/ingest/mcp", payload, nil)
	if err != nil {
		return err
	}
	printJSON(resp)
	return nil
}

func runMerge(args []string) error {
	fs := flag.NewFlagSet("merge", flag.ContinueOnError)
	into := fs.String("into", "main", "target branch")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if fs.NArg() < 1 {
		return fmt.Errorf("merge requires source branch")
	}
	payload := map[string]any{
		"tool": "memory_merge",
		"arguments": map[string]any{
			"source": fs.Arg(0),
			"target": *into,
		},
	}
	resp, err := apiRequest(http.MethodPost, "/api/v1/ingest/mcp", payload, nil)
	if err != nil {
		return err
	}
	printJSON(resp)
	return nil
}

func runSnapshot(args []string) error {
	if len(args) == 0 {
		return fmt.Errorf("snapshot requires subcommand")
	}
	sub := args[0]
	fs := flag.NewFlagSet("snapshot", flag.ContinueOnError)
	branch := fs.String("branch", "main", "branch")
	label := fs.String("label", "", "label")
	if err := fs.Parse(args[1:]); err != nil {
		return err
	}

	var payload map[string]any
	switch sub {
	case "create":
		payload = map[string]any{"tool": "memory_snapshot", "arguments": map[string]any{"branch": *branch, "label": *label}}
	case "list":
		payload = map[string]any{"tool": "memory_snapshot_list", "arguments": map[string]any{"branch": *branch}}
	case "restore":
		if fs.NArg() < 1 {
			return fmt.Errorf("snapshot restore requires snapshot id")
		}
		payload = map[string]any{"tool": "memory_restore", "arguments": map[string]any{"snapshot_id": fs.Arg(0)}}
	default:
		return fmt.Errorf("unsupported snapshot subcommand: %s", sub)
	}

	resp, err := apiRequest(http.MethodPost, "/api/v1/ingest/mcp", payload, nil)
	if err != nil {
		return err
	}
	printJSON(resp)
	return nil
}

func apiRequest(method, path string, payload any, query map[string]string) (any, error) {
	base := strings.TrimRight(apiBaseURL(), "/")
	u, err := url.Parse(base + path)
	if err != nil {
		return nil, err
	}
	if query != nil {
		q := u.Query()
		for k, v := range query {
			if strings.TrimSpace(v) == "" {
				continue
			}
			q.Set(k, v)
		}
		u.RawQuery = q.Encode()
	}

	var body io.Reader
	if payload != nil {
		buf, err := json.Marshal(payload)
		if err != nil {
			return nil, err
		}
		body = bytes.NewReader(buf)
	}

	req, err := http.NewRequest(method, u.String(), body)
	if err != nil {
		return nil, err
	}
	if payload != nil {
		req.Header.Set("Content-Type", "application/json")
	}
	if apiKey := strings.TrimSpace(os.Getenv("DAY1_API_KEY")); apiKey != "" {
		req.Header.Set("X-Day1-API-Key", apiKey)
	}

	resp, err := http.DefaultClient.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	data, err := io.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}
	if resp.StatusCode >= 300 {
		return nil, fmt.Errorf("%s %s failed: status=%d body=%s", method, u.String(), resp.StatusCode, string(data))
	}

	var out any
	if len(data) == 0 {
		return map[string]any{"ok": true}, nil
	}
	if err := json.Unmarshal(data, &out); err != nil {
		return nil, err
	}
	return out, nil
}

func printJSON(value any) {
	data, err := json.MarshalIndent(value, "", "  ")
	if err != nil {
		fmt.Printf("%v\n", value)
		return
	}
	fmt.Println(string(data))
}

func apiBaseURL() string {
	if v := strings.TrimSpace(os.Getenv("DAY1_API_URL")); v != "" {
		return v
	}
	return "http://127.0.0.1:9821"
}

func runCommand(name, dir string, args ...string) error {
	cmd := exec.Command(name, args...)
	cmd.Dir = dir
	cmd.Stdout = os.Stdout
	cmd.Stderr = os.Stderr
	cmd.Stdin = os.Stdin
	return cmd.Run()
}

func strconv(v int) string {
	if v == 0 {
		return "0"
	}
	negative := false
	if v < 0 {
		negative = true
		v = -v
	}
	buf := make([]byte, 0, 12)
	for v > 0 {
		buf = append(buf, byte('0'+v%10))
		v /= 10
	}
	if negative {
		buf = append(buf, '-')
	}
	for i, j := 0, len(buf)-1; i < j; i, j = i+1, j-1 {
		buf[i], buf[j] = buf[j], buf[i]
	}
	return string(buf)
}
