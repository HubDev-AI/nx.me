---
alwaysApply: false
globs: "*.go"
---
Go conventions and idioms — loaded when working with .go files.

# Go Standards

## Interface Conventions

- **Accept interfaces, return structs** — callers define what they need; implementations return concrete types
- **Define interfaces at the consumer**, not the provider — keeps packages decoupled
- **Keep interfaces small** — 1-3 methods; prefer composition of small interfaces

```go
// Consumer defines only what it needs
package user

type UserStore interface {
    Get(key string) ([]byte, error)
    Set(key string, value []byte) error
}

func NewService(store UserStore) *Service {
    return &Service{store: store}
}
```

## Custom Error Types

Use structured error types when callers need programmatic access to error details:

```go
type ValidationError struct {
    Field   string
    Message string
}

func (e *ValidationError) Error() string {
    return fmt.Sprintf("validation: %s — %s", e.Field, e.Message)
}
```

- **Sentinel errors** for comparison: `var ErrNotFound = errors.New("not found")`
- **Check with `errors.Is`** and **extract with `errors.As`** — never compare error strings
- **Wrap with context** using `%w`: `fmt.Errorf("fetch user %s: %w", userID, err)`
