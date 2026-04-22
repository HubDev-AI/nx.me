import type { MetadataRoute } from 'next'

import {
  API_BASE_URL,
  PUBLIC_CARDS_LIST_PATH,
  PUBLIC_MAKEUP_LIST_PATH,
  SITE_URL,
  SITEMAP_MAX_ENTRIES,
  SITEMAP_PAGE_SIZE,
  SITEMAP_REVALIDATE_SECONDS,
} from '@/config/constants'

interface PublicCardListItem {
  username: string
  updated_at: string
}

interface PublicMakeupListItem {
  username: string
  share_hash: string
  publish_rev: number
  updated_at: string
}

interface PublicCardListResponse {
  items: PublicCardListItem[]
  next_cursor: string | null
}

interface PublicMakeupListResponse {
  items: PublicMakeupListItem[]
  next_cursor: string | null
}

/**
 * Fetch one page of the public card listing.
 *
 * Returns null on any failure (network error, non-OK status, malformed JSON).
 * Callers treat null as a terminal error — the sitemap is emitted with
 * whatever has been collected so far, because a partial sitemap is better
 * than a 500 response from the route.
 */
async function fetchCardPage(
  cursor: string | null,
): Promise<PublicCardListResponse | null> {
  const params = new URLSearchParams()
  params.set('per_page', String(SITEMAP_PAGE_SIZE))
  if (cursor) {
    params.set('cursor', cursor)
  }
  const url = `${API_BASE_URL}${PUBLIC_CARDS_LIST_PATH}?${params.toString()}`

  let res: Response
  try {
    res = await fetch(url, {
      next: { revalidate: SITEMAP_REVALIDATE_SECONDS },
    })
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn(`[sitemap] fetch failed for cursor=${cursor ?? 'null'}:`, err)
    return null
  }

  if (!res.ok) {
    // eslint-disable-next-line no-console
    console.warn(
      `[sitemap] listing endpoint returned HTTP ${res.status} for cursor=${cursor ?? 'null'}`,
    )
    return null
  }

  try {
    const json = (await res.json()) as PublicCardListResponse
    if (!Array.isArray(json.items)) {
      // eslint-disable-next-line no-console
      console.warn('[sitemap] listing response missing items[]')
      return null
    }
    return json
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn('[sitemap] failed to parse listing JSON:', err)
    return null
  }
}

async function fetchMakeupPage(
  cursor: string | null,
): Promise<PublicMakeupListResponse | null> {
  const params = new URLSearchParams()
  params.set('per_page', String(SITEMAP_PAGE_SIZE))
  if (cursor) params.set('cursor', cursor)
  const url = `${API_BASE_URL}${PUBLIC_MAKEUP_LIST_PATH}?${params.toString()}`

  let res: Response | undefined
  try {
    res = await fetch(url, { next: { revalidate: SITEMAP_REVALIDATE_SECONDS } })
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn(`[sitemap:makeup] fetch failed for cursor=${cursor ?? 'null'}:`, err)
    return null
  }

  if (!res || !res.ok) {
    // eslint-disable-next-line no-console
    console.warn(`[sitemap:makeup] endpoint returned HTTP ${res?.status ?? 'unknown'}`)
    return null
  }

  try {
    const json = (await res.json()) as PublicMakeupListResponse
    if (!Array.isArray(json.items)) {
      // eslint-disable-next-line no-console
      console.warn('[sitemap:makeup] response missing items[]')
      return null
    }
    return json
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn('[sitemap:makeup] failed to parse JSON:', err)
    return null
  }
}

async function appendGlowupEntries(
  entries: MetadataRoute.Sitemap,
): Promise<void> {
  const maxPages = Math.ceil(SITEMAP_MAX_ENTRIES / SITEMAP_PAGE_SIZE) + 5
  let cursor: string | null = null

  for (let page = 0; page < maxPages; page += 1) {
    const response = await fetchCardPage(cursor)
    if (!response) return

    for (const item of response.items) {
      if (entries.length - 1 >= SITEMAP_MAX_ENTRIES) {
        // eslint-disable-next-line no-console
        console.warn(
          `[sitemap] reached ${SITEMAP_MAX_ENTRIES}-entry cap; additional cards omitted. ` +
            'Future work: emit a sitemap index file to shard across multiple sitemaps.',
        )
        return
      }
      entries.push({
        url: `${SITE_URL}/${item.username}`,
        lastModified: new Date(item.updated_at),
        changeFrequency: 'weekly',
        priority: 0.8,
      })
    }

    if (!response.next_cursor) return
    cursor = response.next_cursor
  }

  // eslint-disable-next-line no-console
  console.warn('[sitemap] hit maxPages safety guard for glowup entries')
}

async function appendMakeupEntries(
  entries: MetadataRoute.Sitemap,
): Promise<void> {
  const maxPages = Math.ceil(SITEMAP_MAX_ENTRIES / SITEMAP_PAGE_SIZE) + 5
  let cursor: string | null = null

  for (let page = 0; page < maxPages; page += 1) {
    const response = await fetchMakeupPage(cursor)
    if (!response) return

    for (const item of response.items) {
      if (entries.length - 1 >= SITEMAP_MAX_ENTRIES) return
      entries.push({
        url: `${SITE_URL}/${item.username}/makeup/${item.share_hash}/${item.publish_rev}`,
        lastModified: new Date(item.updated_at),
        changeFrequency: 'weekly',
        priority: 0.8,
      })
    }

    if (!response.next_cursor) return
    cursor = response.next_cursor
  }

  // eslint-disable-next-line no-console
  console.warn('[sitemap:makeup] hit maxPages safety guard')
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const entries: MetadataRoute.Sitemap = [
    {
      url: SITE_URL,
      lastModified: new Date(),
      changeFrequency: 'daily',
      priority: 1,
    },
  ]

  await appendGlowupEntries(entries)
  await appendMakeupEntries(entries)

  return entries
}
