import { NextResponse } from 'next/server'

import { APP_BUNDLE_ID, APP_LINK_PATHS } from '@/config/constants'

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
 * We claim only the paths the mobile app actually registers as routes
 * (see `APP_LINK_PATHS` + `mobile/app.config.ts`). Claiming every path would
 * capture public share URLs like `/{username}` into the app, which has no
 * matching route — the app would silently 404 instead of opening the browser.
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
          components: APP_LINK_PATHS.map((path) => ({ '/': path })),
        },
      ],
    },
  }

  return NextResponse.json(body, {
    status: 200,
    headers: { 'Content-Type': 'application/json' },
  })
}
