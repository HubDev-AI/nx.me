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
    throw new Error(
      `Failed to fetch card for "${username}": ${res.status} ${res.statusText}`,
    );
  }

  return res.json() as Promise<CardData>;
}
