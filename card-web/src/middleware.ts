import { NextRequest, NextResponse } from 'next/server';

/** Rate-limit window in milliseconds (1 minute). */
const WINDOW_MS = 60_000;

/** Max requests per IP per window. */
const MAX_REQUESTS = 60;

interface WindowEntry {
  count: number;
  resetAt: number;
}

/** In-memory store. Resets on cold-start — acceptable for edge deployment with Vercel KV as future upgrade. */
const ipWindows = new Map<string, WindowEntry>();

function getClientIp(request: NextRequest | Request): string {
  return (
    request.headers.get('x-forwarded-for')?.split(',')[0]?.trim() ??
    request.headers.get('x-real-ip') ??
    '127.0.0.1'
  );
}

function isRateLimited(ip: string): boolean {
  const now = Date.now();
  const entry = ipWindows.get(ip);

  if (!entry || now >= entry.resetAt) {
    ipWindows.set(ip, { count: 1, resetAt: now + WINDOW_MS });
    return false;
  }

  entry.count += 1;
  if (entry.count > MAX_REQUESTS) return true;

  return false;
}

export function middleware(request: NextRequest | Request): NextResponse {
  const url = 'nextUrl' in request ? request.nextUrl : new URL(request.url);
  const { pathname } = url;

  const isCardRoute =
    pathname.startsWith('/public/cards/') ||
    (pathname.match(/^\/[^/]+\//) && !pathname.startsWith('/api/') && !pathname.startsWith('/_next/'));

  if (!isCardRoute) return NextResponse.next();

  const ip = getClientIp(request);
  if (isRateLimited(ip)) {
    return new NextResponse('Too Many Requests', {
      status: 429,
      headers: {
        'Retry-After': '60',
        'Content-Type': 'text/plain',
      },
    });
  }

  return NextResponse.next();
}

export const config = {
  matcher: [
    '/public/cards/:path*',
    '/:username/glow-up/:path*',
    '/:username/makeup/:path*',
  ],
};
