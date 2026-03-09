package storage

import "testing"

func TestParseDatabaseURL_SQLAlchemyStyle(t *testing.T) {
	dsn, err := ParseDatabaseURL("mysql+aiomysql://root:111@localhost:6001/day1")
	if err != nil {
		t.Fatalf("expected no error, got %v", err)
	}
	if dsn == "" {
		t.Fatalf("expected DSN")
	}
	if want := "root:111@tcp(localhost:6001)/day1"; dsn[:len(want)] != want {
		t.Fatalf("unexpected dsn prefix: %s", dsn)
	}
}

func TestParseDatabaseURL_RejectsMissingDB(t *testing.T) {
	if _, err := ParseDatabaseURL("mysql://root:111@localhost:6001"); err == nil {
		t.Fatalf("expected error for missing db name")
	}
}
