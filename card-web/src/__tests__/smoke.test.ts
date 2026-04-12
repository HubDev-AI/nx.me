import { describe, it, expect } from 'vitest'

import { parseCardData } from '@/lib/api'
import { detectPlatform } from '@/lib/user-agent'

const VALID_CARD = {
  username: 'janedoe',
  display_name: 'Jane Doe',
  share_hash: 'abc123',
  before_image_url: 'https://example.com/before.jpg',
  after_image_url: 'https://example.com/after.jpg',
  recommendations: [
    { rank: 1, category: 'Hair', suggestion: 'Try a layered cut' },
  ],
  reaction_count: 42,
  comment_count: 7,
}

describe('parseCardData', () => {
  it('parses a valid card payload', () => {
    const card = parseCardData(VALID_CARD)
    expect(card.username).toBe('janedoe')
    expect(card.display_name).toBe('Jane Doe')
    expect(card.before_image_url).toBe('https://example.com/before.jpg')
    expect(card.after_image_url).toBe('https://example.com/after.jpg')
    expect(card.reaction_count).toBe(42)
    expect(card.comment_count).toBe(7)
    expect(card.recommendations).toHaveLength(1)
    expect(card.recommendations[0]).toEqual({
      rank: 1,
      category: 'Hair',
      suggestion: 'Try a layered cut',
    })
  })

  it('throws when input is not an object', () => {
    expect(() => parseCardData(null)).toThrow('not an object')
    expect(() => parseCardData(['array'])).toThrow('not an object')
    expect(() => parseCardData('string')).toThrow('not an object')
  })

  it('throws on missing required string field', () => {
    // eslint-disable-next-line @typescript-eslint/no-unused-vars -- destructure-to-omit pattern
    const { username: _, ...withoutUsername } = VALID_CARD
    expect(() => parseCardData(withoutUsername)).toThrow('"username"')
  })

  it('throws when recommendations is not an array', () => {
    expect(() =>
      parseCardData({ ...VALID_CARD, recommendations: 'bad' }),
    ).toThrow('"recommendations"')
  })

  it('throws when a recommendation entry is malformed', () => {
    expect(() =>
      parseCardData({
        ...VALID_CARD,
        recommendations: [{ rank: 'not-a-number', category: 'Hair', suggestion: 'Test' }],
      }),
    ).toThrow('rank')
  })
})

describe('detectPlatform', () => {
  it('returns "desktop" when navigator is undefined (server/test env)', () => {
    // In a Node/Vitest environment there is no navigator, so detectPlatform
    // must fall back to "desktop" safely.
    const platform = detectPlatform()
    expect(platform).toBe('desktop')
  })
})
