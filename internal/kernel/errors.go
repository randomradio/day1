package kernel

import "errors"

var (
	ErrMemoryNotFound   = errors.New("memory not found")
	ErrBranchNotFound   = errors.New("branch not found")
	ErrBranchExists     = errors.New("branch already exists")
	ErrInvalidBranch    = errors.New("invalid branch")
	ErrInvalidInput     = errors.New("invalid input")
	ErrSnapshotNotFound = errors.New("snapshot not found")
	ErrRelationNotFound = errors.New("relation not found")
)
