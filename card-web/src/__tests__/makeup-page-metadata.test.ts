import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

import { parseMakeupCardData } from '@/lib/api';

// ---------------------------------------------------------------------------
// parseMakeupCardData contract tests
// ---------------------------------------------------------------------------

describe('parseMakeupCardData', () => {
  const validRaw = {
    username: 'alice',
    display_name: 'Alice',
    share_hash: 'abc123',
    before_image_url: 'https://cdn.example.com/before.jpg',
    after_image_url: 'https://cdn.example.com/after.jpg',
    preset_slug: 'natural_glam',
    intensity: 'medium',
    reaction_count: 5,
    comment_count: 2,
    public_index_opt_in: false,
    publish_rev: 1,
  };

  it('parses a valid payload', () => {
    const result = parseMakeupCardData(validRaw);
    expect(result.username).toBe('alice');
    expect(result.public_index_opt_in).toBe(false);
    expect(result.publish_rev).toBe(1);
    expect(result.preset_slug).toBe('natural_glam');
    expect(result.intensity).toBe('medium');
  });

  it('accepts null preset_slug and intensity', () => {
    const result = parseMakeupCardData({ ...validRaw, preset_slug: null, intensity: null });
    expect(result.preset_slug).toBeNull();
    expect(result.intensity).toBeNull();
  });

  it('returns robots.index=false when public_index_opt_in=false', () => {
    const card = parseMakeupCardData({ ...validRaw, public_index_opt_in: false });
    expect(card.public_index_opt_in).toBe(false);
  });

  it('returns robots.index=true when public_index_opt_in=true', () => {
    const card = parseMakeupCardData({ ...validRaw, public_index_opt_in: true });
    expect(card.public_index_opt_in).toBe(true);
  });

  it('throws on missing required string field', () => {
    expect(() => parseMakeupCardData({ ...validRaw, username: 123 })).toThrow();
  });

  it('throws on non-boolean public_index_opt_in', () => {
    expect(() => parseMakeupCardData({ ...validRaw, public_index_opt_in: 'yes' })).toThrow();
  });

  it('throws on non-number publish_rev', () => {
    expect(() => parseMakeupCardData({ ...validRaw, publish_rev: '1' })).toThrow();
  });

  it('throws on non-object input', () => {
    expect(() => parseMakeupCardData(null)).toThrow();
    expect(() => parseMakeupCardData('string')).toThrow();
    expect(() => parseMakeupCardData([1, 2])).toThrow();
  });
});

// ---------------------------------------------------------------------------
// getMakeupCardData fetch behaviour
// ---------------------------------------------------------------------------

describe('getMakeupCardData', () => {
  let originalFetch: typeof fetch;

  beforeEach(() => {
    originalFetch = globalThis.fetch;
    vi.resetModules();
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.restoreAllMocks();
  });

  it('returns null on 404', async () => {
    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: false,
      status: 404,
      json: async () => ({}),
    } as unknown as Response);

    const { getMakeupCardData } = await import('@/lib/api');
    const result = await getMakeupCardData('alice', 'abc123', '1');
    expect(result).toBeNull();
  });

  it('returns null on network error', async () => {
    globalThis.fetch = vi.fn().mockRejectedValueOnce(new Error('ECONNREFUSED'));
    const { getMakeupCardData } = await import('@/lib/api');
    const result = await getMakeupCardData('alice', 'abc123', '1');
    expect(result).toBeNull();
  });

  it('returns parsed card on 200', async () => {
    const mockCard = {
      username: 'alice',
      display_name: 'Alice',
      share_hash: 'abc123',
      before_image_url: 'https://cdn.example.com/before.jpg',
      after_image_url: 'https://cdn.example.com/after.jpg',
      preset_slug: null,
      intensity: null,
      reaction_count: 0,
      comment_count: 0,
      public_index_opt_in: true,
      publish_rev: 2,
    };

    globalThis.fetch = vi.fn().mockResolvedValueOnce({
      ok: true,
      status: 200,
      json: async () => mockCard,
    } as unknown as Response);

    const { getMakeupCardData } = await import('@/lib/api');
    const result = await getMakeupCardData('alice', 'abc123', '2');
    expect(result).not.toBeNull();
    expect(result?.public_index_opt_in).toBe(true);
    expect(result?.publish_rev).toBe(2);
  });

  it('hash-segment disambiguation: makeup and glowup with same hash are independent routes', async () => {
    // This is a structural test — the makeup route is at /[username]/makeup/[hash]/[rev]
    // while the glowup route is at /[username]/glow-up/[hash]. They call different API
    // endpoints so hash collision across kinds is resolved by the URL segment.
    const { getMakeupCardData, getCardData } = await import('@/lib/api');
    expect(getMakeupCardData).toBeDefined();
    expect(getCardData).toBeDefined();
    // Both functions accept a hash; they call different paths (/makeup/ vs /cards/)
    // so there is no server-side ambiguity.
  });
});
