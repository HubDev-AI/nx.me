import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { SITE_URL } from '@/config/constants'

type FetchMock = ReturnType<typeof vi.fn>

function mockJsonOnce(fetchMock: FetchMock, body: unknown, ok = true, status = 200) {
  fetchMock.mockResolvedValueOnce({
    ok,
    status,
    json: async () => body,
  } as unknown as Response)
}

describe('sitemap', () => {
  let originalFetch: typeof fetch

  beforeEach(() => {
    originalFetch = globalThis.fetch
    vi.resetModules()
  })

  afterEach(() => {
    globalThis.fetch = originalFetch
    vi.restoreAllMocks()
  })

  it('returns only the root URL when backend has no cards', async () => {
    const fetchMock = vi.fn()
    mockJsonOnce(fetchMock, { items: [], next_cursor: null })
    globalThis.fetch = fetchMock as unknown as typeof fetch

    const { default: sitemap } = await import('@/app/sitemap')
    const entries = await sitemap()

    expect(entries).toHaveLength(1)
    expect(entries[0]?.url).toBe(SITE_URL)
    expect(entries[0]?.priority).toBe(1)
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('iterates all pages and emits one entry per username', async () => {
    const fetchMock = vi.fn()
    mockJsonOnce(fetchMock, {
      items: [
        { username: 'alice', updated_at: '2024-01-01T00:00:00Z' },
        { username: 'bob', updated_at: '2024-02-01T00:00:00Z' },
      ],
      next_cursor: 'page2',
    })
    mockJsonOnce(fetchMock, {
      items: [{ username: 'carol', updated_at: '2024-03-01T00:00:00Z' }],
      next_cursor: null,
    })
    globalThis.fetch = fetchMock as unknown as typeof fetch

    const { default: sitemap } = await import('@/app/sitemap')
    const entries = await sitemap()

    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(entries).toHaveLength(4)
    // Root URL first
    expect(entries[0]?.url).toBe(SITE_URL)
    // Card entries follow
    expect(entries[1]?.url).toBe(`${SITE_URL}/alice`)
    expect(entries[1]?.changeFrequency).toBe('weekly')
    expect(entries[1]?.priority).toBe(0.8)
    expect(entries[1]?.lastModified).toBeInstanceOf(Date)
    expect((entries[1]?.lastModified as Date).toISOString()).toBe(
      '2024-01-01T00:00:00.000Z',
    )
    expect(entries[2]?.url).toBe(`${SITE_URL}/bob`)
    expect(entries[3]?.url).toBe(`${SITE_URL}/carol`)

    // Second call must carry the cursor returned by the first
    const secondCallUrl = String(fetchMock.mock.calls[1]?.[0] ?? '')
    expect(secondCallUrl).toContain('cursor=page2')
  })

  it('passes per_page and no cursor on the first page', async () => {
    const fetchMock = vi.fn()
    mockJsonOnce(fetchMock, { items: [], next_cursor: null })
    globalThis.fetch = fetchMock as unknown as typeof fetch

    const { default: sitemap } = await import('@/app/sitemap')
    await sitemap()

    const firstCallUrl = String(fetchMock.mock.calls[0]?.[0] ?? '')
    expect(firstCallUrl).toContain('per_page=1000')
    expect(firstCallUrl).not.toContain('cursor=')
  })

  it('returns partial sitemap on fetch error mid-pagination', async () => {
    const fetchMock = vi.fn()
    mockJsonOnce(fetchMock, {
      items: [{ username: 'alice', updated_at: '2024-01-01T00:00:00Z' }],
      next_cursor: 'page2',
    })
    // Second page fails with non-OK status
    fetchMock.mockResolvedValueOnce({
      ok: false,
      status: 500,
      json: async () => ({}),
    } as unknown as Response)
    globalThis.fetch = fetchMock as unknown as typeof fetch

    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

    const { default: sitemap } = await import('@/app/sitemap')
    const entries = await sitemap()

    // Root + alice only — second page error returns what we have
    expect(entries).toHaveLength(2)
    expect(entries[1]?.url).toBe(`${SITE_URL}/alice`)
    expect(warnSpy).toHaveBeenCalled()
  })

  it('returns partial sitemap when fetch throws (network error)', async () => {
    const fetchMock = vi.fn()
    fetchMock.mockRejectedValueOnce(new Error('ECONNREFUSED'))
    globalThis.fetch = fetchMock as unknown as typeof fetch

    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

    const { default: sitemap } = await import('@/app/sitemap')
    const entries = await sitemap()

    expect(entries).toHaveLength(1)
    expect(entries[0]?.url).toBe(SITE_URL)
    expect(warnSpy).toHaveBeenCalled()
  })

  it('respects the 50k sitemap cap and logs a warning', async () => {
    const fetchMock = vi.fn()
    // Build a page of 1000 users; we'll return 51 pages so the 51st page
    // triggers the cap check while attempting to push the 50,001st card.
    const page = {
      items: Array.from({ length: 1000 }, (_, i) => ({
        username: `user${i}`,
        updated_at: '2024-01-01T00:00:00Z',
      })),
      next_cursor: 'next',
    }
    for (let i = 0; i < 51; i += 1) {
      mockJsonOnce(fetchMock, page)
    }
    globalThis.fetch = fetchMock as unknown as typeof fetch

    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})

    const { default: sitemap } = await import('@/app/sitemap')
    const entries = await sitemap()

    // Root URL + exactly 50,000 card entries
    expect(entries).toHaveLength(50001)
    expect(warnSpy).toHaveBeenCalled()
    const capWarning = warnSpy.mock.calls
      .map((args) => String(args[0]))
      .find((msg) => msg.includes('50000-entry cap'))
    expect(capWarning).toBeDefined()
  })
})
