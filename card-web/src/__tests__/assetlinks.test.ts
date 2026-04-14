import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const ORIGINAL_FINGERPRINTS = process.env.ANDROID_SHA256_FINGERPRINTS

describe('GET /.well-known/assetlinks.json', () => {
  beforeEach(() => {
    vi.resetModules()
  })

  afterEach(() => {
    if (ORIGINAL_FINGERPRINTS === undefined) {
      delete process.env.ANDROID_SHA256_FINGERPRINTS
    } else {
      process.env.ANDROID_SHA256_FINGERPRINTS = ORIGINAL_FINGERPRINTS
    }
  })

  it('returns 404 when ANDROID_SHA256_FINGERPRINTS is unset', async () => {
    delete process.env.ANDROID_SHA256_FINGERPRINTS
    const { GET } = await import('@/app/.well-known/assetlinks.json/route')

    const response = await GET()
    expect(response.status).toBe(404)
  })

  it('returns 404 when ANDROID_SHA256_FINGERPRINTS is empty/whitespace', async () => {
    process.env.ANDROID_SHA256_FINGERPRINTS = ' , , '
    const { GET } = await import('@/app/.well-known/assetlinks.json/route')

    const response = await GET()
    expect(response.status).toBe(404)
  })

  it('returns 200 with a single fingerprint', async () => {
    process.env.ANDROID_SHA256_FINGERPRINTS = 'AA:BB:CC:DD'
    const { GET } = await import('@/app/.well-known/assetlinks.json/route')

    const response = await GET()
    expect(response.status).toBe(200)
    expect(response.headers.get('content-type')).toContain('application/json')

    const body = await response.json()
    expect(Array.isArray(body)).toBe(true)
    expect(body).toHaveLength(1)
    expect(body[0]).toEqual({
      relation: ['delegate_permission/common.handle_all_urls'],
      target: {
        namespace: 'android_app',
        package_name: 'ai.nxme.app',
        sha256_cert_fingerprints: ['AA:BB:CC:DD'],
      },
    })
  })

  it('splits multiple fingerprints on commas and trims whitespace', async () => {
    process.env.ANDROID_SHA256_FINGERPRINTS =
      'AA:BB:CC:DD , EE:FF:00:11 ,  22:33:44:55'
    const { GET } = await import('@/app/.well-known/assetlinks.json/route')

    const response = await GET()
    expect(response.status).toBe(200)

    const body = await response.json()
    expect(body[0]?.target.sha256_cert_fingerprints).toEqual([
      'AA:BB:CC:DD',
      'EE:FF:00:11',
      '22:33:44:55',
    ])
  })

  it('drops empty entries from trailing commas', async () => {
    process.env.ANDROID_SHA256_FINGERPRINTS = 'AA:BB,,EE:FF,'
    const { GET } = await import('@/app/.well-known/assetlinks.json/route')

    const response = await GET()
    expect(response.status).toBe(200)

    const body = await response.json()
    expect(body[0]?.target.sha256_cert_fingerprints).toEqual(['AA:BB', 'EE:FF'])
  })
})
