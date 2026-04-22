import { describe, expect, it, beforeEach, vi } from 'vitest';

function makeRequest(pathname: string, ip = '1.2.3.4'): Request {
  const url = new URL(`https://nxme.ai${pathname}`);
  return new Request(url, {
    headers: { 'x-forwarded-for': ip },
  });
}

describe('middleware rate limiting', () => {
  beforeEach(() => {
    vi.resetModules();
  });

  it('allows requests under the limit', async () => {
    const { middleware } = await import('@/middleware');

    for (let i = 0; i < 60; i++) {
      const req = new Request('https://nxme.ai/alice/makeup/abc/1', {
        headers: { 'x-forwarded-for': '10.0.0.1' },
      });
      const res = middleware(req);
      expect(res.status).not.toBe(429);
    }
  });

  it('returns 429 on the 61st request within the window', async () => {
    const { middleware } = await import('@/middleware');
    const ip = '10.0.0.2';

    for (let i = 0; i < 60; i++) {
      const req = new Request('https://nxme.ai/alice/makeup/abc/1', {
        headers: { 'x-forwarded-for': ip },
      });
      middleware(req);
    }

    const req61 = new Request('https://nxme.ai/alice/makeup/abc/1', {
      headers: { 'x-forwarded-for': ip },
    });
    const res = middleware(req61);
    expect(res.status).toBe(429);
  });

  it('counts per-IP independently', async () => {
    const { middleware } = await import('@/middleware');

    for (let i = 0; i < 60; i++) {
      const req = new Request('https://nxme.ai/alice/makeup/abc/1', {
        headers: { 'x-forwarded-for': '10.0.0.3' },
      });
      middleware(req);
    }

    // Different IP should not be rate-limited
    const req = new Request('https://nxme.ai/alice/makeup/abc/1', {
      headers: { 'x-forwarded-for': '10.0.0.4' },
    });
    const res = middleware(req);
    expect(res.status).not.toBe(429);
  });

  it('non-card routes are not rate-limited', async () => {
    const { middleware } = await import('@/middleware');
    const ip = '10.0.0.5';

    // API routes should pass through (not matched by middleware matcher)
    // Test that the middleware passes through non-card paths
    for (let i = 0; i < 100; i++) {
      const req = makeRequest('/api/revalidate', ip);
      const res = middleware(req);
      // Should not be 429 — api routes are excluded
      expect(res.status).not.toBe(429);
    }
  });
});
