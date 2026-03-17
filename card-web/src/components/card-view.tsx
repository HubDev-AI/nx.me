import Image from 'next/image';

import { type CardData } from '@/lib/api';
import { RECOMMENDATIONS_DISPLAY_COUNT } from '@/config/constants';

interface CardViewProps {
  card: CardData;
}

/**
 * CardView renders the glow-up card:
 * - Before/after image comparison (side-by-side)
 * - Username and display name
 * - Top 5 improvement recommendations
 * - Reaction and comment counts
 */
export function CardView({ card }: CardViewProps) {
  const topRecommendations = card.recommendations
    .slice(0, RECOMMENDATIONS_DISPLAY_COUNT)
    .sort((a, b) => a.rank - b.rank);

  return (
    <article className="w-full max-w-2xl mx-auto space-y-6">
      {/* Identity header */}
      <header className="text-center space-y-1">
        <h1 className="text-2xl font-bold text-content-primary">
          {card.display_name}
        </h1>
        <p className="text-content-secondary text-sm">@{card.username}</p>
      </header>

      {/* Before / After comparison */}
      <section
        aria-label="Before and after comparison"
        className="grid grid-cols-2 gap-3"
      >
        <div className="relative rounded-2xl overflow-hidden aspect-[3/4] bg-surface-elevated">
          {/* Desaturating veil over before image */}
          <div
            className="absolute inset-0 z-10 rounded-2xl"
            style={{ backgroundColor: 'rgba(15, 23, 42, 0.72)' }}
            aria-hidden="true"
          />
          <Image
            src={card.before_image_url}
            alt={`${card.display_name} before glow-up`}
            fill
            className="object-cover"
            sizes="(max-width: 640px) 47vw, 280px"
            priority
          />
          <span className="absolute bottom-3 left-3 z-20 text-xs font-semibold text-before-300 uppercase tracking-wider">
            Before
          </span>
        </div>

        <div className="relative rounded-2xl overflow-hidden aspect-[3/4] bg-surface-elevated">
          {/* Barely-there coral tint over after image */}
          <div
            className="absolute inset-0 z-10 rounded-2xl"
            style={{ backgroundColor: 'rgba(244, 63, 94, 0.08)' }}
            aria-hidden="true"
          />
          <Image
            src={card.after_image_url}
            alt={`${card.display_name} after glow-up`}
            fill
            className="object-cover"
            sizes="(max-width: 640px) 47vw, 280px"
            priority
          />
          {/* Glow ring border */}
          <div
            className="absolute inset-0 z-20 rounded-2xl ring-2"
            style={{ boxShadow: '0 0 0 2px rgba(255, 140, 66, 0.40)' }}
            aria-hidden="true"
          />
          <span className="absolute bottom-3 left-3 z-30 text-xs font-semibold text-after-400 uppercase tracking-wider">
            After
          </span>
        </div>
      </section>

      {/* Engagement counts */}
      <div
        className="flex items-center justify-center gap-6 text-content-secondary text-sm"
        aria-label="Engagement stats"
      >
        <span>
          <strong className="text-content-primary">{card.reaction_count}</strong>{' '}
          reactions
        </span>
        <span aria-hidden="true" className="text-border-strong">
          ·
        </span>
        <span>
          <strong className="text-content-primary">{card.comment_count}</strong>{' '}
          comments
        </span>
      </div>

      {/* Improvement recommendations */}
      {topRecommendations.length > 0 && (
        <section aria-labelledby="recommendations-heading">
          <h2
            id="recommendations-heading"
            className="text-sm font-semibold text-content-secondary uppercase tracking-wider mb-3"
          >
            Top improvements
          </h2>
          <ol className="space-y-3">
            {topRecommendations.map((rec) => (
              <li
                key={rec.rank}
                className="flex gap-3 p-4 rounded-xl bg-surface-card border border-border-default"
              >
                <span
                  className="shrink-0 w-6 h-6 rounded-full flex items-center justify-center text-xs font-bold text-after-500 bg-surface-elevated"
                  aria-label={`Rank ${rec.rank}`}
                >
                  {rec.rank}
                </span>
                <div className="min-w-0">
                  <p className="text-xs font-semibold text-after-400 uppercase tracking-wide mb-0.5">
                    {rec.category}
                  </p>
                  <p className="text-sm text-content-primary leading-relaxed">
                    {rec.suggestion}
                  </p>
                </div>
              </li>
            ))}
          </ol>
        </section>
      )}
    </article>
  );
}
