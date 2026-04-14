import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const ORIGINAL_TEAM_ID = process.env.APPLE_TEAM_ID

describe('GET /.well-known/apple-app-site-association', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  afterEach(() => {
    if (ORIGINAL_TEAM_ID === undefined) {
      delete process.env.APPLE_TEAM_ID
    } else {
      process.env.APPLE_TEAM_ID = ORIGINAL_TEAM_ID
    }
  })

  it('returns 404 when APPLE_TEAM_ID is unset', async () => {
    delete process.env.APPLE_TEAM_ID
    const { GET } = await import('@/app/.well-known/apple-app-site-association/route')

    const response = await GET()
    expect(response.status).toBe(404)
  })

  it('returns 200 with correct JSON shape when APPLE_TEAM_ID is set', async () => {
    process.env.APPLE_TEAM_ID = 'ABC1234567'
    const { GET } = await import('@/app/.well-known/apple-app-site-association/route')

    const response = await GET()
    expect(response.status).toBe(200)
    expect(response.headers.get('content-type')).toContain('application/json')

    const body = await response.json()
    expect(body).toEqual({
      applinks: {
        details: [
          {
            appIDs: ['ABC1234567.ai.nxme.app'],
            components: [{ '/': '*' }],
          },
        ],
      },
    })
  })
})
