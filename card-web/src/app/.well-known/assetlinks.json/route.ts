import { NextResponse } from 'next/server'

import { APP_BUNDLE_ID } from '@/config/constants'

/**
 * GET /.well-known/assetlinks.json
 *
 * Digital-Asset-Links manifest consumed by Android for verified app-links.
 * The folder name includes the `.json` extension literally — Next App Router
 * resolves `{folder}/route.ts` to that exact URL segment, so the path the
 * crawler fetches is `/.well-known/assetlinks.json` with no rewrite needed.
 *
 * When ANDROID_SHA256_FINGERPRINTS is unset we return 404 so Android treats
 * this as "no verified app-links" instead of trusting a half-baked manifest.
 * Multiple fingerprints are supplied as a comma-separated env var — we split,
 * trim, and drop empties so trailing commas or whitespace are tolerated.
 */
export async function GET(): Promise<NextResponse> {
  const raw = process.env.ANDROID_SHA256_FINGERPRINTS
  if (!raw) {
    return new NextResponse(null, { status: 404 })
  }

  const fingerprints = raw
    .split(',')
    .map((fp) => fp.trim())
    .filter((fp) => fp.length > 0)

  if (fingerprints.length === 0) {
    return new NextResponse(null, { status: 404 })
  }

  const body = [
    {
      relation: ['delegate_permission/common.handle_all_urls'],
      target: {
        namespace: 'android_app',
        package_name: APP_BUNDLE_ID,
        sha256_cert_fingerprints: fingerprints,
      },
    },
  ]

  return NextResponse.json(body, {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}
