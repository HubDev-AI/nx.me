---
alwaysApply: false
globs: ["tsconfig*.json", ".eslintrc*", "eslint.config*", "prettier*", ".prettierrc*", "golangci*", "Makefile", "docker-compose*", "Dockerfile*"]
---
Configuration file deviation detection — loaded when reading or modifying config files like tsconfig.json, .eslintrc, prettier.config, golangci.yml, Makefile, or docker-compose.

# Config Deviation Detection

## When This Rule Triggers

Activate when reading or modifying any of these files:

- `tsconfig.json`, `tsconfig.*.json`
- `.eslintrc.*`, `eslint.config.*`
- `prettier.config.*`, `.prettierrc*`
- `golangci.yml`, `.golangci.yml`
- `Makefile`, `Justfile`
- `docker-compose*.yml`, `Dockerfile*`
- `jest.config.*`, `vitest.config.*`
- `package.json` (scripts and config sections)
- `.github/workflows/*.yml`

## Baseline Expectations

### TypeScript (`tsconfig.json`)

Expected strict settings:
```jsonc
{
  "compilerOptions": {
    "strict": true,                        // Non-negotiable
    "noUncheckedIndexedAccess": true,      // Catches undefined from obj[key]
    "noImplicitReturns": true,             // All code paths must return
    "noFallthroughCasesInSwitch": true,    // Prevent switch bugs
    "exactOptionalPropertyTypes": true,    // undefined vs missing distinction
    "noUnusedLocals": true,                // Dead code detection
    "noUnusedParameters": true,            // Dead parameter detection
    "forceConsistentCasingInFileNames": true
  }
}
```

**Deviations to flag:**
- `strict: false` or missing → **Rule 2** (moderate)
- `noUncheckedIndexedAccess` missing → **Rule 1** (minor)
- `any` allowed implicitly (`noImplicitAny: false`) → **Rule 2** (moderate)

### ESLint

Expected baseline:
- Extends `@typescript-eslint/recommended` AND `@typescript-eslint/strict`
- `eslint-plugin-import` configured for import order
- No blanket `eslint-disable` without justification comment
- `no-console` rule enabled (warn or error)

**Deviations to flag:**
- Missing strict preset → **Rule 1** (minor)
- `eslint-disable` without justification → **Rule 2** (moderate)
- No import ordering configured → **Rule 1** (minor)

### Prettier

Adopt existing project config. Flag only when creating a new config (Rule 1).

### Go (`golangci-lint`)

Minimum enabled linters:
```yaml
linters:
  enable:
    - errcheck        # Unchecked errors
    - gosimple        # Simplification suggestions
    - govet           # Suspicious constructs
    - ineffassign     # Unused assignments
    - staticcheck     # Static analysis
    - unused          # Unused code
    - gocritic        # Opinionated linting
    - gofumpt         # Strict formatting
```

**Deviations to flag:**
- `errcheck` disabled → **Rule 2** (moderate) — errors must always be checked
- Missing `staticcheck` → **Rule 1** (minor)
- No linter config at all → **Rule 1** (minor, recommend creating one)

### Docker / Docker Compose

Standard practices (multi-stage, non-root, health checks, pinned tags, `.dockerignore`); flag missing items as Rule 1.

## Detection Pattern

When you read a config file, follow this process:

### Step 1 — Determine Project Status

```
Is this an EXISTING project with established configs?
├── YES → LEARN mode: adopt existing conventions, do not flag
└── NO (new project or creating new config) → CHECK mode: compare against baseline
```

### Step 2 — Compare Against Baseline (CHECK mode only)

For each config file:
1. Read the current values
2. Compare against the baseline expectations above
3. Identify deviations

### Step 3 — Classify and Report

| Impact | Classification | Action |
|---|---|---|
| Style preference (printWidth, quotes) | **Rule 1** — Minor | Log deviation. Do not change. |
| Missing safety setting (strict, errcheck) | **Rule 2** — Moderate | Log + note in checkpoint. Do not auto-fix. |
| Disabled critical protection | **Rule 3** — Significant | Log + amendment in docs/amendments.md |
| Fundamentally different architecture | **Rule 4** — Architectural | HALT — ask user |

### Step 4 — Report Format

```
[CONFIG DEVIATION] {file}: {setting}
  Expected: {baseline_value}
  Actual:   {current_value}
  Rule:     {1|2|3|4}
  Action:   {logged|noted|amendment|HALT}
  Reason:   {why this matters}
```

## Critical Rules

- **NEVER auto-fix config files** — deviations may be intentional team decisions
- **LEARN before you flag** — if the project has 100+ commits with a config, it's established
- **Ask before changing** — config changes affect the entire team
- **Document reasoning** — if you recommend a change, explain the impact of not changing
- **Respect lock files** — never modify `package-lock.json`, `yarn.lock`, `go.sum` manually
