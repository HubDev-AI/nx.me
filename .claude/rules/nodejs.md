---
alwaysApply: false
globs: ["*.ts", "*.js", "*.mjs", "*.cjs"]
---
Node.js and TypeScript conventions — loaded when working with .ts or .js files.

# Node.js / TypeScript Standards

## ESLint Configuration

- Use `@typescript-eslint/recommended` + `@typescript-eslint/strict` presets as baseline
- Enable `eslint-plugin-import` for import ordering enforcement
- Require justification comment for every `eslint-disable-next-line`
- Prefer `@typescript-eslint/consistent-type-imports` for type-only imports

## Import Order

Enforce with `eslint-plugin-import/order`, separated by blank lines:

1. Node.js built-ins (always `node:` prefix — `import fs from 'node:fs'`, not `'fs'`)
2. External packages
3. Internal aliases (`@internal/`, `@company/`, `@app/`)
4. Relative imports

## Result Pattern for Business Logic

Prefer discriminated unions over throwing for expected business errors:

```typescript
type Result<T, E = Error> =
  | { ok: true; value: T }
  | { ok: false; error: E };
```

Reserve `throw` for truly exceptional situations (programmer errors, infrastructure failures).

## Error Types

```typescript
export class AppError extends Error {
  constructor(
    message: string,
    public readonly code: string,
    public readonly statusCode: number = 500,
    options?: ErrorOptions,
  ) {
    super(message, options);
    this.name = this.constructor.name;
  }
}

export class NotFoundError extends AppError {
  constructor(resource: string, id: string, options?: ErrorOptions) {
    super(`${resource} '${id}' not found`, 'NOT_FOUND', 404, options);
  }
}
```

- Include error codes for programmatic handling
- Preserve stack traces via `cause` option
- Map to HTTP status codes at the handler layer, not in domain code
- **No `!` (non-null assertions) in production code** — allowed only in test files
