/**
 * Mock card API — dev only.
 *
 * Returns deterministic card data for any username, using a simple hash
 * to pick from image pools and recommendation templates. Same username
 * always returns the same card; different usernames give different data.
 *
 * Usage: GET /api/mock/cards/sophia → CardData JSON
 */
import { type NextRequest, NextResponse } from 'next/server';

import { type CardData } from '@/lib/api';

// ── Guard: dev only ────────────────────────────────────────────────────
if (process.env.NODE_ENV === 'production') {
  throw new Error('Mock card API must not be loaded in production');
}

// ── Deterministic hash from a string ───────────────────────────────────
function hash(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h + s.charCodeAt(i)) | 0;
  }
  return Math.abs(h);
}

function pickSeeded<T>(arr: T[], seed: number, offset = 0): T {
  return arr[(seed + offset) % arr.length]!;
}

// ── Before/after image pairs (from public/images/) ─────────────────────
const PAIRS = [
  // Men
  ...([1, 2, 3, 4, 9, 11, 12, 13, 17, 19, 22, 35, 37, 39].map(n => ({
    before: `/images/before-${n}.jpg`,
    after: `/images/after-${n}.jpg`,
  }))),
  // Women
  ...([5, 6, 7, 8, 10, 14, 15, 20, 28, 29, 30, 31, 34, 40].map(n => ({
    before: `/images/before-${n}.jpg`,
    after: `/images/after-${n}.jpg`,
  }))),
  // Young
  ...([41, 42, 43, 44, 45, 46, 47, 48, 49, 50, 51, 52].map(n => ({
    before: `/images/before-${n}.jpg`,
    after: `/images/after-${n}.jpg`,
  }))),
  // Young women
  ...([53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63, 65, 66, 67, 68, 69, 70, 71, 72].map(n => ({
    before: `/images/before-${n}.jpg`,
    after: `/images/after-${n}.jpg`,
  }))),
];

// ── Display names ──────────────────────────────────────────────────────
const DISPLAY_NAMES = [
  'Sophia Rivera', 'Marcus Chen', 'Aisha Patel', 'Liam O\'Brien',
  'Yuki Tanaka', 'Zara Williams', 'Noah Kim', 'Priya Sharma',
  'Diego Santos', 'Freya Jensen', 'Kai Nakamura', 'Elena Volkov',
  'Omar Hassan', 'Luna Martinez', 'Ethan Park', 'Maya Robinson',
  'Ren Watanabe', 'Amara Okafor', 'Felix Andersen', 'Isla Campbell',
  'Arjun Mehta', 'Chloe Dupont', 'Rafael Costa', 'Noor Al-Rashid',
];

// ── Recommendation templates ───────────────────────────────────────────
const RECOMMENDATIONS: Array<{ category: string; suggestion: string }> = [
  { category: 'Hairstyle', suggestion: 'Try a textured mid-length cut with side-swept layers for a more dynamic silhouette that frames your face shape beautifully.' },
  { category: 'Hairstyle', suggestion: 'A soft curtain fringe would complement your face shape — ask your stylist for a center-parted layered cut.' },
  { category: 'Hairstyle', suggestion: 'Consider a modern shag cut with face-framing pieces to add movement and dimension.' },
  { category: 'Clothing', suggestion: 'Swap the oversized tee for a well-fitted linen button-down in a warm earth tone — instant polish without trying too hard.' },
  { category: 'Clothing', suggestion: 'A structured blazer over a simple crew-neck tee creates an effortlessly put-together look for any occasion.' },
  { category: 'Clothing', suggestion: 'Invest in a tailored pair of wide-leg trousers — they balance proportions and work from office to dinner.' },
  { category: 'Grooming', suggestion: 'A consistent skincare routine with SPF 30+ daily and vitamin C serum will give you a noticeable glow within weeks.' },
  { category: 'Grooming', suggestion: 'Shape your brows with a professional wax — well-groomed brows are the single highest-impact facial change.' },
  { category: 'Grooming', suggestion: 'Try a tinted lip balm in a shade close to your natural lip color for a subtle but polished finish.' },
  { category: 'Accessories', suggestion: 'A minimal gold pendant necklace adds just enough detail to elevate a plain outfit without looking overdone.' },
  { category: 'Accessories', suggestion: 'Swap plastic frames for a pair of acetate tortoiseshell glasses — same comfort, ten times the style.' },
  { category: 'Accessories', suggestion: 'A quality leather watch strap in cognac or tan adds warmth and intention to any casual outfit.' },
  { category: 'Color Palette', suggestion: 'Your skin undertone is warm — build around terracotta, olive, mustard, and cream instead of cool blues and grays.' },
  { category: 'Color Palette', suggestion: 'Deep jewel tones like burgundy, emerald, and sapphire would complement your complexion beautifully.' },
  { category: 'Fit', suggestion: 'Your jeans are a size too large — get them tapered from the knee down for a cleaner line without sacrificing comfort.' },
  { category: 'Fit', suggestion: 'Hemming your trousers to just above the shoe creates a cleaner silhouette — it\'s a small alteration with big impact.' },
  { category: 'Layering', suggestion: 'Add a lightweight knit cardigan in a neutral tone as a transitional layer — it bridges seasons and adds depth.' },
  { category: 'Footwear', suggestion: 'White leather sneakers with a chunky sole would modernize your casual looks — keep them clean for maximum effect.' },
  { category: 'Footwear', suggestion: 'A pair of Chelsea boots in suede instantly elevates jeans and a sweater from casual to date-night ready.' },
  { category: 'Posture', suggestion: 'Stand with shoulders back and chin parallel to the ground — better posture alone makes any outfit look 2x more intentional.' },
];

// ── Route handler ──────────────────────────────────────────────────────
export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ username: string }> },
) {
  const { username } = await params;
  const h = hash(username);

  const pair = pickSeeded(PAIRS, h);
  const displayName = pickSeeded(DISPLAY_NAMES, h);

  // Pick 5–7 unique recommendations
  const recCount = 5 + (h % 3);
  const recs: CardData['recommendations'] = [];
  const used = new Set<number>();
  for (let i = 0; recs.length < recCount; i++) {
    const idx = (h + i * 7) % RECOMMENDATIONS.length;
    if (!used.has(idx)) {
      used.add(idx);
      recs.push({ rank: recs.length + 1, ...RECOMMENDATIONS[idx]! });
    }
  }

  const card: CardData = {
    username,
    display_name: displayName,
    before_image_url: pair.before,
    after_image_url: pair.after,
    recommendations: recs,
    reaction_count: 10 + (h % 500),
    comment_count: 1 + (h % 80),
  };

  return NextResponse.json(card);
}
