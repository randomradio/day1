package storage

import (
	"fmt"
	"net"
	"net/url"
	"strings"
)

// ParseDatabaseURL converts SQLAlchemy/MySQL style URLs into go-sql-driver/mysql DSN.
func ParseDatabaseURL(raw string) (string, error) {
	trimmed := strings.TrimSpace(raw)
	if trimmed == "" {
		return "", fmt.Errorf("database url is empty")
	}

	trimmed = strings.TrimPrefix(trimmed, "mysql+aiomysql://")
	trimmed = strings.TrimPrefix(trimmed, "mysql+pymysql://")
	if !strings.Contains(trimmed, "://") {
		trimmed = "mysql://" + trimmed
	}

	u, err := url.Parse(trimmed)
	if err != nil {
		return "", fmt.Errorf("parse database url: %w", err)
	}

	if u.Scheme != "mysql" {
		return "", fmt.Errorf("unsupported database scheme %q", u.Scheme)
	}

	dbName := strings.TrimPrefix(u.Path, "/")
	if dbName == "" {
		return "", fmt.Errorf("database name is missing in url")
	}

	host := u.Host
	if host == "" {
		host = "127.0.0.1:3306"
	}
	if _, _, err := net.SplitHostPort(host); err != nil {
		host = net.JoinHostPort(host, "3306")
	}

	user := ""
	pass := ""
	if u.User != nil {
		user = u.User.Username()
		pass, _ = u.User.Password()
	}

	query := u.Query()
	if query.Get("parseTime") == "" {
		query.Set("parseTime", "true")
	}
	if query.Get("charset") == "" {
		query.Set("charset", "utf8mb4")
	}
	if query.Get("loc") == "" {
		query.Set("loc", "UTC")
	}

	auth := user
	if pass != "" {
		auth = fmt.Sprintf("%s:%s", user, pass)
	}
	if auth == "" {
		auth = "root"
	}
	return fmt.Sprintf("%s@tcp(%s)/%s?%s", auth, host, dbName, query.Encode()), nil
}
