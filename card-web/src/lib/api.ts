import {
  API_BASE_URL,
  API_FETCH_TIMEOUT_MS,
  CARD_REVALIDATE_SECONDS,
  HTTP_NOT_FOUND,
} from '@/config/constants';

export interface Recommendation {
  rank: number;
  category: string;
  suggestion: string;
}

export interface CardData {
  username: string;
  display_name: string;
  share_hash: string;
  before_image_url: string;
  after_image_url: string;
  recommendations: Recommendation[];
  reaction_count: number;
  comment_count: number;
}

export interface MakeupCardData {
  username: string;
  display_name: string;
  share_hash: string;
  before_image_url: string;
  after_image_url: string;
  preset_slug: string | null;
  intensity: string | null;
  reaction_count: number;
  comment_count: number;
  public_index_opt_in: boolean;
  publish_rev: number;
}

export function getMakeupCacheTags(username: string, shareHash?: string): string[] {
  const baseTag = `makeup:${username}`;
  if (!shareHash) return [baseTag];
  return [baseTag, `${baseTag}:${shareHash}`];
}

export async function getMakeupCardData(
  username: string,
  shareHash: string,
  rev: string,
): Promise<MakeupCardData | null> {
  const path = `/api/public/makeup/${encodeURIComponent(username)}/${encodeURIComponent(shareHash)}/${encodeURIComponent(rev)}`;
  const url = `${API_BASE_URL}${path}`;

  let res: Response;
  try {
    res = await fetch(url, {
      next: {
        revalidate: CARD_REVALIDATE_SECONDS,
        tags: getMakeupCacheTags(username, shareHash),
      },
      signal: AbortSignal.timeout(API_FETCH_TIMEOUT_MS),
    });
  } catch (err) {
    if (process.env.NODE_ENV !== 'production') {
      // eslint-disable-next-line no-console
      console.warn(`[api] getMakeupCardData("${username}") fetch failed:`, err);
    }
    return null;
  }

  if (res.status === HTTP_NOT_FOUND) return null;

  if (!res.ok) {
    // eslint-disable-next-line no-console
    console.warn(`[api] getMakeupCardData("${username}") returned HTTP ${res.status}`);
    return null;
  }

  try {
    const json: unknown = await res.json();
    return parseMakeupCardData(json);
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn(`[api] getMakeupCardData("${username}") parse failed:`, err);
    return null;
  }
}

export function parseMakeupCardData(raw: unknown): MakeupCardData {
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new Error('MakeupCardData contract violation: response is not an object');
  }

  const obj = raw as Record<string, unknown>;

  assertField(obj, 'username', 'string');
  assertField(obj, 'display_name', 'string');
  assertField(obj, 'share_hash', 'string');
  assertField(obj, 'before_image_url', 'string');
  assertField(obj, 'after_image_url', 'string');
  assertField(obj, 'reaction_count', 'number');
  assertField(obj, 'comment_count', 'number');
  assertField(obj, 'public_index_opt_in', 'boolean');
  assertField(obj, 'publish_rev', 'number');

  return {
    username: obj['username'] as string,
    display_name: obj['display_name'] as string,
    share_hash: obj['share_hash'] as string,
    before_image_url: obj['before_image_url'] as string,
    after_image_url: obj['after_image_url'] as string,
    preset_slug: typeof obj['preset_slug'] === 'string' ? obj['preset_slug'] : null,
    intensity: typeof obj['intensity'] === 'string' ? obj['intensity'] : null,
    reaction_count: obj['reaction_count'] as number,
    comment_count: obj['comment_count'] as number,
    public_index_opt_in: obj['public_index_opt_in'] as boolean,
    publish_rev: obj['publish_rev'] as number,
  };
}

export function getCardCacheTags(username: string, shareHash?: string): string[] {
  const baseTag = `card:${username}`;
  if (!shareHash) {
    return [baseTag];
  }
  return [baseTag, `${baseTag}:${shareHash}`];
}

/**
 * Fetch public card data for a given username.
 *
 * Returns `null` for ANY failure — network errors, non-OK HTTP status,
 * malformed responses, backend down, etc.  This guarantees the SSR render
 * never blocks or throws due to backend state, so the landing page and
 * server startup are always fast.
 */
export async function getCardData(username: string, shareHash?: string): Promise<CardData | null> {
  const path = shareHash
    ? `/api/public/cards/${encodeURIComponent(username)}/${encodeURIComponent(shareHash)}`
    : `/api/public/cards/${encodeURIComponent(username)}`;
  const url = `${API_BASE_URL}${path}`;

  let res: Response;
  try {
    res = await fetch(url, {
      next: {
        revalidate: CARD_REVALIDATE_SECONDS,
        tags: getCardCacheTags(username, shareHash),
      },
      signal: AbortSignal.timeout(API_FETCH_TIMEOUT_MS),
    });
  } catch (err) {
    // Network-level failures (ECONNREFUSED, timeout, DNS) — the backend is
    // unreachable.  Return null so the page renders the not-found / error UI
    // instead of hanging or crashing the SSR render.
    if (process.env.NODE_ENV !== 'production') {
      // eslint-disable-next-line no-console
      console.warn(`[api] getCardData("${username}") fetch failed:`, err);
    }
    return null;
  }

  if (res.status === HTTP_NOT_FOUND) {
    return null;
  }

  if (!res.ok) {
    // eslint-disable-next-line no-console
    console.warn(
      `[api] getCardData("${username}") returned HTTP ${res.status}`,
    );
    return null;
  }

  try {
    const json: unknown = await res.json();
    return parseCardData(json);
  } catch (err) {
    // eslint-disable-next-line no-console
    console.warn(`[api] getCardData("${username}") parse failed:`, err);
    return null;
  }
}

function assertField(
  obj: Record<string, unknown>,
  field: string,
  expectedType: string,
): void {
  if (typeof obj[field] !== expectedType) {
    throw new Error(
      `CardData contract violation: expected "${field}" to be ${expectedType}, got ${typeof obj[field]}`,
    );
  }
}

export function parseCardData(raw: unknown): CardData {
  if (raw === null || typeof raw !== 'object' || Array.isArray(raw)) {
    throw new Error('CardData contract violation: response is not an object');
  }

  const obj = raw as Record<string, unknown>;

  assertField(obj, 'username', 'string');
  assertField(obj, 'display_name', 'string');
  assertField(obj, 'share_hash', 'string');
  assertField(obj, 'before_image_url', 'string');
  assertField(obj, 'after_image_url', 'string');
  assertField(obj, 'reaction_count', 'number');
  assertField(obj, 'comment_count', 'number');

  if (!Array.isArray(obj['recommendations'])) {
    throw new Error(
      'CardData contract violation: expected "recommendations" to be an array',
    );
  }

  const recommendations = (obj['recommendations'] as unknown[]).map(
    (item, index) => {
      if (item === null || typeof item !== 'object' || Array.isArray(item)) {
        throw new Error(
          `CardData contract violation: recommendations[${index}] is not an object`,
        );
      }
      const rec = item as Record<string, unknown>;
      if (typeof rec['rank'] !== 'number') {
        throw new Error(
          `CardData contract violation: recommendations[${index}].rank must be a number, got ${typeof rec['rank']}`,
        );
      }
      if (typeof rec['category'] !== 'string') {
        throw new Error(
          `CardData contract violation: recommendations[${index}].category must be a string, got ${typeof rec['category']}`,
        );
      }
      if (typeof rec['suggestion'] !== 'string') {
        throw new Error(
          `CardData contract violation: recommendations[${index}].suggestion must be a string, got ${typeof rec['suggestion']}`,
        );
      }
      return { rank: rec['rank'], category: rec['category'], suggestion: rec['suggestion'] } as Recommendation;
    },
  );

  return {
    username: obj['username'] as string,
    display_name: obj['display_name'] as string,
    share_hash: obj['share_hash'] as string,
    before_image_url: obj['before_image_url'] as string,
    after_image_url: obj['after_image_url'] as string,
    recommendations,
    reaction_count: obj['reaction_count'] as number,
    comment_count: obj['comment_count'] as number,
  };
}
