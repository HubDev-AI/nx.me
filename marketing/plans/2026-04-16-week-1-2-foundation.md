# Week 1–2 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute the first 2 weeks of the 90-day pre-launch warmup. Lock the positioning, retune the TikTok autoresearch loop for faceless content, ship a waitlist landing page, publish the first 14 short-form posts, and set up the weekly-review process.

**Architecture:** Marketing foundation split across three surfaces — (1) `marketing/` for strategy + research + reviews, (2) `tools/tiktok-autoresearch/` for autonomous content generation, (3) `card-web/` for the waitlist landing page + email capture. Backend data lives in Supabase via a new `waitlist` migration.

**Tech Stack:** Python (autoresearch), Next.js 14 App Router + Tailwind (card-web), Supabase Postgres + anon RLS policy (waitlist storage), CapCut Pro / ElevenLabs (video production), Buffer or Later (cross-posting).

---

## File structure

### Create
- `app/migrations/0038_waitlist.sql` — Supabase table + anon-insert RLS policy
- `card-web/src/app/api/waitlist/route.ts` — POST handler, inserts signup
- `card-web/src/components/WaitlistForm.tsx` — client form, email + submit
- `card-web/src/__tests__/waitlist-form.test.tsx` — unit test for form
- `card-web/src/__tests__/waitlist-api.test.ts` — API route test
- `marketing/reviews/2026-04-19-week-1.md` — first Sunday review
- `marketing/reviews/_template.md` — review template
- `marketing/content/2026-04-week-1.md` — week 1 content outline (14 posts)

### Modify
- `tools/tiktok-autoresearch/strategy.md` — pillar split 55/20/25/0, faceless-feasibility scoring, retire BIP content type
- `tools/tiktok-autoresearch/prompts/hooks.txt` — drop POV archetype, add faceless rubric note
- `tools/tiktok-autoresearch/prompts/calendar.txt` — new pillar split
- `card-web/src/app/page.tsx` — swap App Store CTA for waitlist email form while pre-launch
- `card-web/src/config/constants.ts` — add WAITLIST_ENABLED flag (default true)

---

### Task 1: Retune `tools/tiktok-autoresearch/strategy.md` for faceless + new pillar split

**Files:**
- Modify: `tools/tiktok-autoresearch/strategy.md`

**Why:** Strategy §3 and §5 require pillars 55/20/25/0 and a `faceless-feasibility` score. The existing strategy.md still carries 40/30/20/10 and BIP. This is the lever the autoresearch loop reads every iteration — wrong file, wrong content.

- [ ] **Step 1: Read the current strategy.md to confirm sections to change**

Run: `cat tools/tiktok-autoresearch/strategy.md`
Confirm the `## Content Pillars` section shows the old 40/30/20/10 split.

- [ ] **Step 2: Rewrite `## Content Pillars`**

Replace the existing pillar section with:

```markdown
## Content Pillars

Faceless-native content distribution (no founder on camera this phase).

1. **Education (55%)** — Face shape science, 468-landmark visualizations,
   explainer voiceovers over motion graphics. Faceless-native. The wedge
   carrier.
2. **Transformation reveals (20%)** — Before/after posts. Gated on having
   consented beta users; ramps up once the app hits beta (target D60).
3. **Trend participation (25%)** — Stitches and duets of LooksMax / face-
   rating / glow-up creators. High algorithmic lift, zero on-camera time.
4. **Build-in-public / BTS (0%)** — RETIRED this phase. Re-enable only if
   this strategy doc is updated.
```

- [ ] **Step 3: Add a new `## Faceless-feasibility scoring` section**

Append after `## Scoring Rubrics`:

```markdown
### Faceless-feasibility (2 pts, added to every rubric)

Every content artifact must be shootable without a founder on camera.

- **2 pts** — fully producible with screen-rec, motion graphics, voiceover,
  or consented stock/user footage.
- **1 pt** — producible faceless but requires an additional asset we don't
  yet own (e.g., a consented user video).
- **0 pts** — requires a person on camera. REJECT.

This dimension is weighted EQUAL to the other 5 dimensions in each rubric.
A hook that scores 10/10 on curiosity but 0/2 on faceless-feasibility is
discarded.
```

- [ ] **Step 4: Update the `## Tone & Voice` section**

Add one bullet at the end of the existing list:

```markdown
- **Engineer-authored, not personality-driven** — The brand voice this phase is
  technical + warm, not charismatic + on-camera. Prefer "we measure 468
  landmarks" framings over "I'm going to show you" framings.
```

- [ ] **Step 5: Add a new `## Verbatim-backed positioning angles` section**

Insert a new section after `## Brand Identity`. Copy the 8-angle table
from `marketing/strategy.md` §1 verbatim (keep the pain ranks and
candidate lines). This gives the LLM the approved angles to bias hooks
toward.

- [ ] **Step 6: Smoke-test the loop reads the new strategy**

Run: `cd tools/tiktok-autoresearch && python run.py hooks -n 2`
Expected: 2 new hook iterations in `results/` with no founder-on-camera
archetypes (no "POV" openers, no "me when"). Both iterations should score
≥1 on faceless-feasibility.

If a POV hook slips through, iterate: the prompt change in Task 2 will
reinforce.

- [ ] **Step 7: Commit**

```bash
git add tools/tiktok-autoresearch/strategy.md
git commit -m "feat(autoresearch): faceless-native pillar split + scoring"
```

---

### Task 2: Update `hooks.txt` and `calendar.txt` prompt files

**Files:**
- Modify: `tools/tiktok-autoresearch/prompts/hooks.txt`
- Modify: `tools/tiktok-autoresearch/prompts/calendar.txt`

**Why:** The prompts currently include POV archetypes and the old 40/30/20/10 calendar split. Rules in strategy.md are not enforced unless the prompt matches.

- [ ] **Step 1: Edit `hooks.txt` — remove POV archetype**

Find the `1. **POV hooks:**` line in the "Hook archetypes to explore" list
and delete that entire bullet (2 lines). Leave the other 9 archetypes
intact. Renumber 2→1 through 10→9.

- [ ] **Step 2: Edit `hooks.txt` — add faceless constraint**

Add this block immediately after the "Hook archetypes to explore" list:

```
## Faceless constraint (mandatory)

Every hook you generate must be shootable without a human face on camera.
Valid visual modes:
- Screen recording of the NXME app analysis
- Text overlay on stock / b-roll footage
- Motion graphics with MediaPipe-style landmark overlays
- Voiceover narration over any of the above

Reject (give score 0 on faceless-feasibility) any hook whose default
execution implies "founder looks at camera" or "person narrates to the
lens." If a hook CAN be adapted to faceless, adapt it in the hook text
itself — don't just mention the constraint in the notes.
```

- [ ] **Step 3: Edit `calendar.txt` — update pillar split**

Find the pillar split section. Replace 40/30/20/10 with 55/20/25/0.
Mirror the exact language from the strategy.md §3 table.

- [ ] **Step 4: Smoke-test both prompts**

```bash
cd tools/tiktok-autoresearch
python run.py hooks -n 3
python run.py calendar -n 2
```

Expected: zero POV hooks in the 3 iterations. Calendar output reflects
the new split.

- [ ] **Step 5: Commit**

```bash
git add tools/tiktok-autoresearch/prompts/hooks.txt tools/tiktok-autoresearch/prompts/calendar.txt
git commit -m "feat(autoresearch): prompts enforce faceless + new pillar split"
```

---

### Task 3: Waitlist database migration

**Files:**
- Create: `app/migrations/0038_waitlist.sql`

**Why:** Waitlist signups need a durable store the landing page can write to and the launch-day email sequence can read from. Supabase is already the project's data layer; reusing it avoids adding Mailchimp / ConvertKit now.

- [ ] **Step 1: Write the migration**

Create `app/migrations/0038_waitlist.sql` with:

```sql
-- 0038_waitlist.sql — pre-launch waitlist capture
-- Consumed by: card-web/src/app/api/waitlist/route.ts (insert-only)
-- Consumed by: marketing launch-day email export

create table if not exists public.waitlist (
    id            uuid primary key default gen_random_uuid(),
    email         citext not null unique,
    source        text,                 -- e.g. 'tiktok-bio', 'landing-hero'
    referrer      text,                 -- HTTP referer at submission time
    created_at    timestamptz not null default now()
);

create index if not exists waitlist_created_at_idx
    on public.waitlist (created_at desc);

alter table public.waitlist enable row level security;

-- Anon can insert. Nobody (including anon) can read. Service role reads
-- via admin export only.
create policy "anon can insert waitlist"
    on public.waitlist
    for insert
    to anon
    with check (true);

comment on table public.waitlist is
    'Pre-launch email capture from card-web landing page. Read-only via service role.';
```

- [ ] **Step 2: Run the migration locally**

```bash
make migrate
```

Expected: `0038_waitlist.sql` applied, no errors.

- [ ] **Step 3: Verify the table + policy**

```bash
psql "postgresql://postgres:postgres@localhost:54322/postgres" -c '\d public.waitlist'
psql "postgresql://postgres:postgres@localhost:54322/postgres" -c "select polname, polcmd from pg_policy where polrelid = 'public.waitlist'::regclass;"
```

Expected: table exists with the 5 columns above; one policy named `anon can insert waitlist` for command `a` (insert).

- [ ] **Step 4: Commit**

```bash
git add app/migrations/0038_waitlist.sql
git commit -m "feat(db): waitlist table with anon-insert RLS policy"
```

---

### Task 4: Waitlist API route (card-web)

**Files:**
- Create: `card-web/src/app/api/waitlist/route.ts`
- Create: `card-web/src/__tests__/waitlist-api.test.ts`

**Why:** The landing-page form submits to this route. Route validates, inserts, returns success. Tested with a vitest unit against a mock Supabase client.

- [ ] **Step 1: Write the failing test**

Create `card-web/src/__tests__/waitlist-api.test.ts`:

```typescript
import { describe, expect, it, vi } from 'vitest';

import { POST } from '@/app/api/waitlist/route';

function makeRequest(body: unknown, headers: Record<string, string> = {}): Request {
  return new Request('http://localhost/api/waitlist', {
    method: 'POST',
    body: JSON.stringify(body),
    headers: { 'Content-Type': 'application/json', ...headers },
  });
}

describe('POST /api/waitlist', () => {
  it('rejects missing email with 400', async () => {
    const res = await POST(makeRequest({}));
    expect(res.status).toBe(400);
  });

  it('rejects malformed email with 400', async () => {
    const res = await POST(makeRequest({ email: 'not-an-email' }));
    expect(res.status).toBe(400);
  });

  it('accepts a well-formed email with 200', async () => {
    vi.stubEnv('SUPABASE_URL', 'http://localhost:54321');
    vi.stubEnv('SUPABASE_ANON_KEY', 'anon-key-stub');
    // For this first test we mock the Supabase insert via a module mock:
    vi.doMock('@supabase/supabase-js', () => ({
      createClient: () => ({
        from: () => ({
          insert: async () => ({ data: null, error: null }),
        }),
      }),
    }));

    const res = await POST(
      makeRequest(
        { email: 'test@example.com', source: 'landing-hero' },
        { referer: 'https://nxme.ai/' },
      ),
    );
    expect(res.status).toBe(200);
  });
});
```

- [ ] **Step 2: Run the test, confirm it fails**

```bash
cd card-web && npm run test -- waitlist-api
```

Expected: FAIL — `Cannot find module '@/app/api/waitlist/route'`.

- [ ] **Step 3: Implement the route**

Create `card-web/src/app/api/waitlist/route.ts`:

```typescript
import { createClient } from '@supabase/supabase-js';

import { SUPABASE_URL, SUPABASE_ANON_KEY } from '@/config/env';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export async function POST(request: Request): Promise<Response> {
  let payload: unknown;
  try {
    payload = await request.json();
  } catch {
    return Response.json({ error: 'invalid_json' }, { status: 400 });
  }

  const email = typeof (payload as { email?: unknown }).email === 'string'
    ? ((payload as { email: string }).email.trim().toLowerCase())
    : '';
  const source = typeof (payload as { source?: unknown }).source === 'string'
    ? (payload as { source: string }).source
    : null;

  if (!EMAIL_RE.test(email)) {
    return Response.json({ error: 'invalid_email' }, { status: 400 });
  }

  const referer = request.headers.get('referer');
  const supabase = createClient(SUPABASE_URL, SUPABASE_ANON_KEY);
  const { error } = await supabase
    .from('waitlist')
    .insert({ email, source, referrer: referer });

  if (error && error.code !== '23505') {
    // 23505 = unique_violation (duplicate email) — treat as success
    return Response.json({ error: 'insert_failed' }, { status: 500 });
  }

  return Response.json({ ok: true }, { status: 200 });
}
```

- [ ] **Step 4: Add `SUPABASE_URL` / `SUPABASE_ANON_KEY` to env loader**

If `card-web/src/config/env.ts` does not yet export those constants, add
them. No fallbacks — throw if missing (per project convention).

```typescript
function required(name: string): string {
  const value = process.env[name];
  if (!value) throw new Error(`Missing required env: ${name}`);
  return value;
}

export const SUPABASE_URL = required('SUPABASE_URL');
export const SUPABASE_ANON_KEY = required('SUPABASE_ANON_KEY');
```

Add the new vars to `card-web/.env.example`.

- [ ] **Step 5: Run the test, confirm it passes**

```bash
cd card-web && npm run test -- waitlist-api
```

Expected: PASS (3/3).

- [ ] **Step 6: Commit**

```bash
git add card-web/src/app/api/waitlist/route.ts \
        card-web/src/__tests__/waitlist-api.test.ts \
        card-web/src/config/env.ts \
        card-web/.env.example
git commit -m "feat(card-web): POST /api/waitlist with email validation + Supabase insert"
```

---

### Task 5: Waitlist form component + landing page integration

**Files:**
- Create: `card-web/src/components/WaitlistForm.tsx`
- Create: `card-web/src/__tests__/waitlist-form.test.tsx`
- Modify: `card-web/src/app/page.tsx`
- Modify: `card-web/src/config/constants.ts`

**Why:** Swap the pre-launch CTA on the existing photography-driven landing page from "Get the app" (dead links pre-launch) to "Join the waitlist" (email form). Keep the existing before/after transformation section — it's already on-brand.

- [ ] **Step 1: Add `WAITLIST_ENABLED` flag**

Edit `card-web/src/config/constants.ts`. Add:

```typescript
export const WAITLIST_ENABLED = true;
```

This lets us flip back to App Store CTAs on launch day by toggling one
constant. No env fallback — the constant is the source of truth.

- [ ] **Step 2: Write the failing component test**

Create `card-web/src/__tests__/waitlist-form.test.tsx`:

```typescript
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { WaitlistForm } from '@/components/WaitlistForm';

describe('WaitlistForm', () => {
  it('renders email input and submit button', () => {
    render(<WaitlistForm source="test" />);
    expect(screen.getByPlaceholderText(/email/i)).toBeDefined();
    expect(screen.getByRole('button', { name: /join/i })).toBeDefined();
  });

  it('posts to /api/waitlist on submit', async () => {
    const fetchMock = vi
      .spyOn(global, 'fetch')
      .mockResolvedValue(new Response(JSON.stringify({ ok: true }), { status: 200 }));

    render(<WaitlistForm source="test" />);
    fireEvent.change(screen.getByPlaceholderText(/email/i), {
      target: { value: 'test@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: /join/i }));

    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
    const [url, init] = fetchMock.mock.calls[0];
    expect(url).toBe('/api/waitlist');
    expect(JSON.parse((init as RequestInit).body as string)).toMatchObject({
      email: 'test@example.com',
      source: 'test',
    });
  });

  it('shows a success message after 200', async () => {
    vi.spyOn(global, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ ok: true }), { status: 200 }),
    );

    render(<WaitlistForm source="test" />);
    fireEvent.change(screen.getByPlaceholderText(/email/i), {
      target: { value: 'test@example.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: /join/i }));

    await waitFor(() => {
      expect(screen.getByText(/you're in/i)).toBeDefined();
    });
  });
});
```

- [ ] **Step 3: Run the test, confirm it fails**

```bash
cd card-web && npm run test -- waitlist-form
```

Expected: FAIL — `Cannot find module '@/components/WaitlistForm'`.

- [ ] **Step 4: Implement the component**

Create `card-web/src/components/WaitlistForm.tsx`:

```tsx
'use client';

import { useState } from 'react';

type Status = 'idle' | 'submitting' | 'success' | 'error';

export function WaitlistForm({ source }: { source: string }): JSX.Element {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<Status>('idle');

  async function onSubmit(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    setStatus('submitting');
    try {
      const res = await fetch('/api/waitlist', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, source }),
      });
      setStatus(res.ok ? 'success' : 'error');
    } catch {
      setStatus('error');
    }
  }

  if (status === 'success') {
    return <p className="text-sm text-white/80">You're in. We'll email when it's ready.</p>;
  }

  return (
    <form onSubmit={onSubmit} className="flex flex-col sm:flex-row gap-3 max-w-md">
      <input
        type="email"
        required
        placeholder="Your email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        className="flex-1 px-4 py-3 rounded-full bg-white/10 text-white placeholder-white/40 border border-white/10 focus:border-[var(--accent)] outline-none text-sm"
      />
      <button
        type="submit"
        disabled={status === 'submitting'}
        className="px-6 py-3 rounded-full text-[#0a0a0a] text-sm font-medium disabled:opacity-60"
        style={{ backgroundColor: 'var(--accent)' }}
      >
        {status === 'submitting' ? 'Joining…' : 'Join the waitlist'}
      </button>
      {status === 'error' && (
        <p className="text-sm text-red-300 self-center">Try again in a second.</p>
      )}
    </form>
  );
}
```

- [ ] **Step 5: Wire the form into the landing page hero**

Edit `card-web/src/app/page.tsx`. Find the hero block (around lines
45–58, the `<div className="mt-8 flex items-center gap-6">` block with
`APP_STORE_URL` / `PLAY_STORE_URL` links). Replace that block with:

```tsx
{WAITLIST_ENABLED ? (
  <div className="mt-8">
    <WaitlistForm source="landing-hero" />
    <p className="mt-3 text-xs text-white/30">No trial ambush. No spam.</p>
  </div>
) : (
  <div className="mt-8 flex items-center gap-6">
    {/* existing App Store + Play Store links */}
    {/* ...kept for launch day when WAITLIST_ENABLED flips to false... */}
  </div>
)}
```

Add the imports at the top of the file:

```tsx
import { WaitlistForm } from '@/components/WaitlistForm';
import { WAITLIST_ENABLED } from '@/config/constants';
```

Also update the hero subcopy on line 42–44 to replace:

```tsx
AI-powered style recommendations. See your transformation before you commit.
```

with the verbatim-backed version:

```tsx
Your face, upgraded — not replaced. 468-landmark analysis. Same photo, same answer.
```

(Source: `marketing/strategy.md` §1 angles 2 & 3.)

- [ ] **Step 6: Run the tests, confirm all pass**

```bash
cd card-web && npm run test
```

Expected: all pass, including new waitlist-form + waitlist-api tests.

- [ ] **Step 7: Manually verify locally**

```bash
# Terminal 1 — backend + Supabase
make up

# Terminal 2 — card-web
cd card-web && npm run dev
```

Open http://localhost:3006. Confirm:
1. Hero shows the new subcopy.
2. "Join the waitlist" form appears instead of the App Store button.
3. Submitting a valid email → "You're in" message.
4. Check Supabase Studio (http://localhost:54323) → `public.waitlist`
   table has the row.

- [ ] **Step 8: Commit**

```bash
git add card-web/src/components/WaitlistForm.tsx \
        card-web/src/__tests__/waitlist-form.test.tsx \
        card-web/src/app/page.tsx \
        card-web/src/config/constants.ts
git commit -m "feat(card-web): waitlist hero form + verbatim-backed subcopy"
```

---

### Task 6: Draft Week 1 content outline (14 posts)

**Files:**
- Create: `marketing/content/2026-04-week-1.md`

**Why:** The autoresearch loop generates hooks; it doesn't decide which
14 get filmed this week. This task produces the content outline — posts
1–14 — distributed across the new 55/20/25/0 pillar split, using the
8 verbatim-backed angles as seed concepts.

- [ ] **Step 0: Set up cross-post scheduling (one-time)**

Sign up for Buffer free tier (https://buffer.com/pricing — free plan
covers 3 channels). Connect: TikTok, Instagram, YouTube (Shorts). If
TikTok isn't supported on free tier (check at time of setup), use Later
free tier as fallback (https://later.com/) which historically has
supported TikTok on free. Verify one test post queues successfully
across all three from the dashboard.

Log the chosen tool in `marketing/reviews/_template.md` under a new
"Tooling" footer so future reviews remember where posts are scheduled.

- [ ] **Step 1: Generate 50 hooks with the retuned autoresearch loop**

```bash
cd tools/tiktok-autoresearch
python run.py hooks -n 50
```

Output: `tools/tiktok-autoresearch/results/hooks-YYYY-MM-DD.{tsv,md}`.

- [ ] **Step 2: Cherry-pick 14 hooks mapped to pillars**

Open the markdown output. Select:
- **8 Education posts** (55%) — hooks that frame face-shape science,
  468-landmark reasoning, or Qoves-style detailed analysis
- **0 Transformation posts** (gated on beta users — not yet)
- **4 Trend posts** (25%) — stitches/duets of LooksMax / face-rating
  content
- **2 flex** — either Education or Trend; pick what's highest-scoring

Drop any hook whose faceless-feasibility score < 2. Drop any hook that
uses poisoned vocabulary (score, rating, beautify, free trial).

- [ ] **Step 3: Write the content outline**

Create `marketing/content/2026-04-week-1.md`:

```markdown
# Week 1 content outline — 14 posts

Dates: Apr 16 – Apr 22. Cadence: 2 posts/day, ~11am + 7pm ET.

Cross-post every post to IG Reels + YT Shorts same day.

## Post index

| # | Date | Time | Pillar | Hook | Format | Asset needs | Status |
|---|------|------|--------|------|--------|-------------|--------|
| 1 | Apr 16 | 11am | Education | "Most face shape charts are completely wrong. Here's what 468 landmarks actually measure." | Screen-rec + VO | MediaPipe 468-landmark visualization clip | [ ] |
| 2 | Apr 16 | 7pm  | Trend     | Stitch: [highest-view LooksMax video this week] — "This is why your rating is different every time." | Stitch + text overlay | Source video | [ ] |
| ... | ... | ... | ... | ... | ... | ... | [ ] |
| 14 | Apr 22 | 7pm | Education | "The jawline myth: what your 'weak jaw' actually measures." | Motion graphics + VO | Landmark overlay asset | [ ] |
```

Fill rows 3–13 with the cherry-picked hooks from step 2.

- [ ] **Step 4: Commit**

```bash
git add marketing/content/2026-04-week-1.md
git commit -m "docs(marketing): week 1 content outline — 14 posts"
```

---

### Task 7: Weekly-review template + first Sunday baseline

**Files:**
- Create: `marketing/reviews/_template.md`
- Create: `marketing/reviews/2026-04-19-week-1.md`

**Why:** Strategy §6 requires a Sunday 1-hour review. A shared template
keeps it cheap to do every week. First review on Apr 19 records the
baseline metrics (zero-state) we'll compare against going forward.

- [ ] **Step 1: Write the review template**

Create `marketing/reviews/_template.md`:

```markdown
# Week [N] review — [YYYY-MM-DD]

Covers: [start date] – [end date].

## Metrics snapshot

| Metric | This week | Last week | Δ |
|---|---|---|---|
| Median views per post | | | |
| TikTok net-new followers | | | |
| Bio-link CTR (%) | | | |
| Waitlist conversions / bio-click (%) | | | |
| Waitlist total | | | |

## Top post
- Title: [hook]
- Pillar: [Education / Trend / Transformation]
- Views / comments / saves: [numbers]
- Why it worked: [1-2 sentences]

## Lowest post
- Title:
- Why it flopped:

## Top 3 hook archetypes driving reach this week
1. [archetype]
2. [archetype]
3. [archetype]

## Strategy / autoresearch updates made
- [change, one line each]

## Risk triggers to watch (from strategy.md §8)
- [note any hits or near-hits]

## Next week's content outline queued?
- [ ] yes (link to `content/YYYY-MM-week-N.md`)
```

- [ ] **Step 2: Write the first review — Apr 19**

Copy the template to `marketing/reviews/2026-04-19-week-1.md`. Fill
metrics with the baseline (mostly zeros — we're 4 days into posting).
Record which 4 posts went live, what their early view counts look like,
and any obvious pattern already emerging. Note: this first review has
less than a full 7-day window — flag that.

- [ ] **Step 3: Commit**

```bash
git add marketing/reviews/_template.md marketing/reviews/2026-04-19-week-1.md
git commit -m "docs(marketing): weekly-review template + week 1 baseline"
```

---

## Post-plan checkpoint

After all 7 tasks complete, verify:

- [ ] `make test` passes (backend — should be unaffected, but regression-check)
- [ ] `cd card-web && npm run test` passes (card-web — new tests included)
- [ ] `cd card-web && npm run lint` passes
- [ ] `cd card-web && npm run type-check` passes
- [ ] Local smoke: waitlist signup end-to-end (landing form → Supabase row)
- [ ] 4+ posts have actually gone live on TikTok (with cross-posts to IG Reels + YT Shorts)
- [ ] Next week's content outline queued in `marketing/content/2026-04-week-2.md`
- [ ] PR opened against `dev` with all commits above

At that point, Week 1–2 foundation is done. Hand off to the
Week 3–4 "Volume ramp" plan (to be written when Week 1–2 lands).

---

## Out of scope for this plan

Explicitly not in Week 1–2:
- Free face-shape tool / SEO landing pages (Option B — revisit D60)
- Creator seeding outreach (Option C — revisit post-launch)
- Paid ads (post-launch, small tests only)
- Email sequence for waitlist (Week 9 — `email-sequence` skill owns it)
- Product Hunt / PR outreach (Week 9+)
- App Store listing (Week 9+ — `aso-audit` skill owns it)
- Follow-up customer-research pass for female-skew audience (queued in
  `marketing/research/README.md` — do when someone can run PRAW with auth)

---

## References

- Strategy: [`marketing/strategy.md`](../strategy.md)
- Product-marketing context: [`marketing/product-marketing-context.md`](../product-marketing-context.md)
- Research synthesis: [`marketing/research/README.md`](../research/README.md)
- Autoresearch tool: [`tools/tiktok-autoresearch/`](../../tools/tiktok-autoresearch/)
- Skill library: [`marketing/skills/`](../skills/)
