/**
 * Dev gallery — renders many card variations on one page for design review.
 *
 * Fetches real card data from the backend for all demo users.
 * Visit /dev/gallery in development to see all variations at once.
 */
import { type Metadata } from 'next';

import { CardView } from '@/components/card-view';
import { buildTheme } from '@/components/theme-provider';
import { getCardData } from '@/lib/api';

export const dynamic = 'force-dynamic';

export const metadata: Metadata = {
  title: 'Card Gallery — Dev',
  robots: 'noindex',
};

// ── Production guard ───────────────────────────────────────────────────
if (process.env.NODE_ENV === 'production') {
  throw new Error('Dev gallery must not be loaded in production');
}

// ── Demo usernames to display ──────────────────────────────────────────
const DEMO_USERNAMES = [
  'sophia', 'marcus', 'aisha', 'liam', 'yuki', 'zara',
  'noah_k', 'priya', 'diego', 'freya', 'kai_n', 'elena_v',
];

// ── Page ───────────────────────────────────────────────────────────────
export default async function GalleryPage() {
  const cards = await Promise.all(
    DEMO_USERNAMES.map(async (username) => {
      const card = await getCardData(username);
      const theme = buildTheme();
      return { card, accent: theme.accent };
    }),
  );

  const validCards = cards.filter((c) => c.card !== null);

  return (
    <div className="min-h-screen bg-[#050505] text-[#e8e8e8]">
      {/* Header */}
      <header className="sticky top-0 z-50 bg-[#050505]/90 backdrop-blur-md border-b border-white/[0.06] px-6 py-4">
        <div className="max-w-7xl mx-auto flex items-center justify-between">
          <div>
            <h1 className="font-display text-xl text-white">Card Gallery</h1>
            <p className="text-xs text-[#555] mt-0.5">
              {validCards.length} variations — dev only
            </p>
          </div>
          <div className="text-xs text-[#555]">
            URL: <code className="text-[#888]">/&#123;user&#125;/glow-up/&#123;hash&#125;</code>
          </div>
        </div>
      </header>

      {/* Card grid */}
      <main className="max-w-7xl mx-auto px-6 py-12">
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-8">
          {validCards.map(({ card, accent }) => {
            if (!card) return null;
            const fullPageUrl = `/${card.username}/glow-up/${card.share_hash}`;
            return (
              <div
                key={card.username}
                className="bg-[#0a0a0a] rounded-2xl p-6 sm:p-8 border border-white/[0.04] hover:border-white/[0.08] transition-colors"
                style={{ '--accent': accent } as React.CSSProperties}
              >
                {/* Color swatch + link */}
                <div className="flex items-center justify-between mb-6">
                  <div className="flex items-center gap-2">
                    <span
                      className="w-3 h-3 rounded-full"
                      style={{ backgroundColor: accent }}
                    />
                    <span className="text-xs text-[#555] font-mono">{accent}</span>
                  </div>
                  <a
                    href={fullPageUrl}
                    className="text-xs text-[#555] hover:text-white/60 transition-colors"
                  >
                    {card.share_hash} &rarr;
                  </a>
                </div>

                <CardView card={card} />
              </div>
            );
          })}
        </div>
      </main>
    </div>
  );
}
