# Napkin

## Corrections
| Date | Source | What Went Wrong | What To Do Instead |
|------|--------|----------------|-------------------|
| 2026-03-19 | Session | N/A - first session | N/A |

## User Preferences
- NEXT_TURBOPACK=0 for production builds (Turbopack not used)
- Port 3006 for local production testing

## Patterns That Work
- `prefetch={false}` on all Link components pointing to external URLs or anchors to prevent Next.js from attempting RSC prefetches that hit the [username] dynamic route
- `object-[center_20%]` for portrait hero images (keeps faces framed vs object-top cutting foreheads)

## Patterns That Don't Work
- `object-top` on hero portraits -- crops foreheads
- Default Link prefetch behavior in pages with dynamic catch-all routes -- causes hangs when backend is unreachable

## Domain Notes
- card-web is a Next.js 14 landing page + shareable card viewer
- `[username]` route fetches from backend API with 3s timeout (API_FETCH_TIMEOUT_MS)
- API_BASE_URL defaults to https://api.nxme.ai when env vars not set
- Theme provider picks random theme client-side (useEffect on mount)
- Build output: / is static, /[username] is dynamic server-rendered
