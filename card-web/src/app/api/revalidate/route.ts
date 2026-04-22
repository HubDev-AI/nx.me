import { timingSafeEqual } from 'node:crypto';

import { revalidatePath, revalidateTag } from 'next/cache';
import { NextRequest, NextResponse } from 'next/server';

import { getCardCacheTags, getMakeupCacheTags } from '@/lib/api';

// Security notes:
// - M-17: Uses timing-safe comparison to prevent brute-force via timing side-channel
// - M-18: Rate limiting should be configured at infra level (Vercel/CDN WAF)
// - No CSRF needed — uses shared secret header, not cookies. Server-to-server only.

/**
 * POST /api/revalidate
 *
 * On-demand revalidation endpoint called by the backend when a card is deleted
 * or updated. Immediately purges the ISR cache for `/{username}`.
 *
 * Request headers:
 *   x-revalidation-secret: <REVALIDATION_SECRET env var>
 *
 * Request body (JSON):
 *   { "username": string }
 *
 * Responses:
 *   200 { revalidated: true, username: string }
 *   400 { error: "username is required" }
 *   401 { error: "Unauthorized" }
 */
export async function POST(request: NextRequest): Promise<NextResponse> {
  const secret = request.headers.get('x-revalidation-secret') ?? '';
  const expectedSecret = process.env.REVALIDATION_SECRET ?? '';

  const secretBuf = Buffer.from(secret);
  const expectedBuf = Buffer.from(expectedSecret);
  if (
    !expectedSecret ||
    secretBuf.length !== expectedBuf.length ||
    !timingSafeEqual(secretBuf, expectedBuf)
  ) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  let username: string | undefined;
  let shareHash: string | undefined;
  let kind: string | undefined;
  let publishRev: number | undefined;

  try {
    const body = (await request.json()) as Record<string, unknown>;
    if (typeof body.username === 'string' && body.username.trim().length > 0) {
      username = body.username.trim();
    }
    if (typeof body.share_hash === 'string') shareHash = body.share_hash.trim();
    if (typeof body.kind === 'string') kind = body.kind.trim();
    if (typeof body.publish_rev === 'number') publishRev = body.publish_rev;
  } catch {
    // JSON parse failure — fall through to validation error below
  }

  if (!username) {
    return NextResponse.json(
      { error: 'username is required' },
      { status: 400 },
    );
  }

  // Validate username format: alphanumeric + underscores, max 64 chars
  const USERNAME_PATTERN = /^[a-zA-Z0-9_]{1,64}$/;
  if (!USERNAME_PATTERN.test(username)) {
    return NextResponse.json(
      { error: 'Invalid username format' },
      { status: 400 },
    );
  }

  if (kind === 'makeup' && shareHash && publishRev !== undefined) {
    for (const tag of getMakeupCacheTags(username, shareHash)) {
      revalidateTag(tag);
    }
    revalidatePath(`/${username}/makeup/${shareHash}/${publishRev}`);
  } else {
    for (const tag of getCardCacheTags(username)) {
      revalidateTag(tag);
    }
    revalidatePath(`/${username}`);
  }

  return NextResponse.json({ revalidated: true, username });
}
