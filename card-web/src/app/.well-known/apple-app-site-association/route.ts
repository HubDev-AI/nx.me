import { NextResponse } from 'next/server'

import { APP_BUNDLE_ID } from '@/config/constants'

/**
 * GET /.well-known/apple-app-site-association
 *
 * Universal-links association file consumed by iOS during app install /
 * update.  Apple requires:
 *   - Content-Type: application/json (NOT application/json+extended — that's
 *     legacy handoff-only and breaks modern universal links).
 *   - HTTPS delivery (handled at the edge).
 *   - No redirects (Next handles the route directly).
 *
 * We emit a config that claims every path on this origin for the native app.
 * When APPLE_TEAM_ID is unset (e.g. pre-launch, CI) we return 404 rather than
 * a malformed file — Apple treats a bad file as "no universal links".
 */
export async function GET(): Promise<NextResponse> {
  const teamId = process.env.APPLE_TEAM_ID
  if (!teamId) {
    return new NextResponse(null, { status: 404 })
  }

  const body = {
    applinks: {
      details: [
        {
          appIDs: [`${teamId}.${APP_BUNDLE_ID}`],
          components: [{ '/': '*' }],
        },
      ],
    },
  }

  return NextResponse.json(body, {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}
