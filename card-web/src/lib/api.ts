import {
  API_BASE_URL,
  CARD_REVALIDATE_SECONDS,
  HTTP_GONE,
} from '@/config/constants';

export interface Recommendation {
  rank: number;
  category: string;
  suggestion: string;
}

export interface CardData {
  username: string;
  display_name: string;
  before_image_url: string;
  after_image_url: string;
  recommendations: Recommendation[];
  reaction_count: number;
  comment_count: number;
}

/**
 * Fetch public card data for a given username.
 *
 * Returns `null` when the card has been deleted (HTTP 410).
 * Throws for any other non-OK status so that Next.js error.tsx can handle it.
 */
export async function getCardData(username: string): Promise<CardData | null> {
  const url = `${API_BASE_URL}/api/public/cards/${encodeURIComponent(username)}`;

  const res = await fetch(url, {
    next: { revalidate: CARD_REVALIDATE_SECONDS },
  });

  if (res.status === HTTP_GONE) {
    return null;
  }

  if (res.status === 404) {
    return null;
  }

  if (!res.ok) {
    throw new Error("Unable to load this card. Please try again later.");
  }

  const json: unknown = await res.json();
  return parseCardData(json);
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
    before_image_url: obj['before_image_url'] as string,
    after_image_url: obj['after_image_url'] as string,
    recommendations,
    reaction_count: obj['reaction_count'] as number,
    comment_count: obj['comment_count'] as number,
  };
}
