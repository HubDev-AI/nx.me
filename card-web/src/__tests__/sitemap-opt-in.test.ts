import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { SITE_URL } from '@/config/constants';

type FetchMock = ReturnType<typeof vi.fn>;

function mockJsonOnce(fetchMock: FetchMock, body: unknown, ok = true) {
  fetchMock.mockResolvedValueOnce({
    ok,
    status: ok ? 200 : 500,
    json: async () => body,
  } as unknown as Response);
}

describe('sitemap makeup opt-in', () => {
  let originalFetch: typeof fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    vi.resetModules();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('includes opted-in makeup slug and excludes non-opted-in', async () => {
    const fetchMock = vi.fn();
    // Glowup page: no cards
    mockJsonOnce(fetchMock, { items: [], next_cursor: null });
    // Makeup page: one opted-in post
    mockJsonOnce(fetchMock, {
      items: [
        {
          username: 'alice',
          share_hash: 'abc123',
          publish_rev: 2,
          updated_at: '2026-04-21T00:00:00Z',
        },
      ],
      next_cursor: null,
    });
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const { default: sitemap } = await import('@/app/sitemap');
    const entries = await sitemap();

    const makeupUrl = `${SITE_URL}/alice/makeup/abc123/2`;
    const glowupUrl = `${SITE_URL}/alice`;

    expect(entries.some((e) => e.url === makeupUrl)).toBe(true);
    expect(entries.some((e) => e.url === glowupUrl)).toBe(false);
  });

  it('does not include makeup entries when makeup API returns empty', async () => {
    const fetchMock = vi.fn();
    // Glowup page
    mockJsonOnce(fetchMock, {
      items: [{ username: 'bob', updated_at: '2026-04-20T00:00:00Z' }],
      next_cursor: null,
    });
    // Makeup page: empty
    mockJsonOnce(fetchMock, { items: [], next_cursor: null });
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const { default: sitemap } = await import('@/app/sitemap');
    const entries = await sitemap();

    const hasMakeup = entries.some((e) => e.url.includes('/makeup/'));
    expect(hasMakeup).toBe(false);

    const bobUrl = `${SITE_URL}/bob`;
    expect(entries.some((e) => e.url === bobUrl)).toBe(true);
  });

  it('includes makeup URL with correct rev in path', async () => {
    const fetchMock = vi.fn();
    mockJsonOnce(fetchMock, { items: [], next_cursor: null });
    mockJsonOnce(fetchMock, {
      items: [
        { username: 'carol', share_hash: 'xyz789', publish_rev: 5, updated_at: '2026-04-22T00:00:00Z' },
      ],
      next_cursor: null,
    });
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const { default: sitemap } = await import('@/app/sitemap');
    const entries = await sitemap();

    expect(entries.some((e) => e.url === `${SITE_URL}/carol/makeup/xyz789/5`)).toBe(true);
  });

  it('partial sitemap: makeup entries still appended if glowup fetch fails', async () => {
    const fetchMock = vi.fn();
    // Glowup fetch fails
    fetchMock.mockRejectedValueOnce(new Error('network'));
    // Makeup page succeeds
    mockJsonOnce(fetchMock, {
      items: [
        { username: 'dave', share_hash: 'dddd', publish_rev: 1, updated_at: '2026-04-21T00:00:00Z' },
      ],
      next_cursor: null,
    });

    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {});
    globalThis.fetch = fetchMock as unknown as typeof fetch;

    const { default: sitemap } = await import('@/app/sitemap');
    const entries = await sitemap();

    expect(entries.some((e) => e.url === `${SITE_URL}/dave/makeup/dddd/1`)).toBe(true);
    expect(warnSpy).toHaveBeenCalled();
  });
});
