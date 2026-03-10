package kernel

import (
	"context"
	"strings"
)

type userIDContextKey struct{}

// WithUserID returns a context carrying the authenticated user ID.
func WithUserID(ctx context.Context, userID string) context.Context {
	return context.WithValue(ctx, userIDContextKey{}, strings.TrimSpace(userID))
}

// UserIDFromContext returns the user ID from context if present.
func UserIDFromContext(ctx context.Context) string {
	if ctx == nil {
		return ""
	}
	value := ctx.Value(userIDContextKey{})
	userID, ok := value.(string)
	if !ok {
		return ""
	}
	return strings.TrimSpace(userID)
}
