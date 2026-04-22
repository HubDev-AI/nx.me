import Image from 'next/image';

import { RECOMMENDATIONS_DISPLAY_COUNT } from '@/config/constants';
import { type CardData, type MakeupCardData } from '@/lib/api';

type AnyCardData = CardData | MakeupCardData;

interface CardViewProps {
  card: AnyCardData;
  kind?: 'glowup' | 'makeup';
}

export function CardView({ card, kind = 'glowup' }: CardViewProps) {
  const isMakeup = kind === 'makeup';
  const beforeAlt = `${card.display_name} before ${isMakeup ? 'makeup' : 'glow-up'}`;
  const afterAlt = `${card.display_name} after ${isMakeup ? 'makeup' : 'glow-up'}`;

  const topRecommendations = ('recommendations' in card ? card.recommendations : [])
    .toSorted((a, b) => a.rank - b.rank)
    .slice(0, RECOMMENDATIONS_DISPLAY_COUNT);

  return (
    <article className="w-full max-w-2xl mx-auto">
      {/* Identity header */}
      <header className="text-center mb-10">
        <h1 className="font-display text-4xl sm:text-5xl tracking-[-0.02em] text-white leading-[0.95]">
          {card.display_name}
        </h1>
        <p className="mt-2 text-sm text-content-tertiary tracking-wide">
          @{card.username}
        </p>
      </header>

      {/* Before / After comparison */}
      <section
        aria-label="Before and after comparison"
        className="grid grid-cols-2 gap-3 sm:gap-4"
      >
        {/* Before image */}
        <div className="relative rounded-xl overflow-hidden aspect-[3/4] bg-surface-card">
          <Image
            src={card.before_image_url}
            alt={beforeAlt}
            fill
            className="object-cover"
            sizes="(max-width: 640px) 47vw, 280px"
            priority
          />
          <div
            className="absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-surface-page/70 to-transparent"
            aria-hidden="true"
          />
          <span className="absolute bottom-3 left-3 z-10 text-[11px] font-medium text-content-secondary uppercase tracking-widest">
            Before
          </span>
        </div>

        {/* After image */}
        <div className="relative rounded-xl overflow-hidden aspect-[3/4] bg-surface-card">
          <Image
            src={card.after_image_url}
            alt={afterAlt}
            fill
            className="object-cover"
            sizes="(max-width: 640px) 47vw, 280px"
            priority
          />
          <div
            className="absolute inset-x-0 bottom-0 h-16 bg-gradient-to-t from-surface-page/70 to-transparent"
            aria-hidden="true"
          />
          <span className="absolute bottom-3 left-3 z-10 text-[11px] font-medium uppercase tracking-widest" style={{ color: 'var(--accent)' }}>
            After
          </span>
        </div>
      </section>

      {/* Engagement counts */}
      <div
        className="flex items-center justify-center gap-6 mt-8 text-sm"
        aria-label="Engagement stats"
      >
        <span className="flex items-center gap-1.5">
          <strong className="text-white font-semibold">
            {card.reaction_count}
          </strong>
          <span className="text-content-tertiary">reactions</span>
        </span>
        <span className="text-content-faint" aria-hidden="true">/</span>
        <span className="flex items-center gap-1.5">
          <strong className="text-white font-semibold">
            {card.comment_count}
          </strong>
          <span className="text-content-tertiary">comments</span>
        </span>
      </div>

      {/* Improvement recommendations */}
      {topRecommendations.length > 0 && (
        <section aria-labelledby="recommendations-heading" className="mt-12">
          <h2
            id="recommendations-heading"
            className="text-xs tracking-[0.25em] uppercase text-content-tertiary mb-8"
          >
            Top improvements
          </h2>
          <ol className="space-y-0">
            {topRecommendations.map((rec, index) => (
              <li
                key={rec.rank}
                className={[
                  'flex gap-4 py-5',
                  index > 0 ? 'border-t border-white/[0.06]' : '',
                ].join(' ')}
              >
                <span
                  className="shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-semibold text-content-inverse"
                  aria-label={`Rank ${rec.rank}`}
                  style={{ backgroundColor: 'var(--accent)' }}
                >
                  {rec.rank}
                </span>
                <div className="min-w-0">
                  <p
                    className="text-[11px] font-semibold uppercase tracking-wider mb-1"
                    style={{ color: 'var(--accent)' }}
                  >
                    {rec.category}
                  </p>
                  <p className="text-sm text-content-muted leading-relaxed">
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
