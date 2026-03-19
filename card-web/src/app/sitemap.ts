import type { MetadataRoute } from 'next'

import { SITE_URL } from '@/config/constants'

// TODO: Fetch public usernames from API to include /{username} card pages.
// The backend does not currently expose a public listing endpoint, so only
// the root URL is included for now. When an endpoint like
// GET /api/public/cards (paginated) exists, iterate it here to add every
// card page entry.
export default function sitemap(): MetadataRoute.Sitemap {
  return [
    {
      url: SITE_URL,
      lastModified: new Date(),
      changeFrequency: 'daily',
      priority: 1,
    },
  ]
}
