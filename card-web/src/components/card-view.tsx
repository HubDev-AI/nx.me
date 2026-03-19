import Image from 'next/image';

import { RECOMMENDATIONS_DISPLAY_COUNT } from '@/config/constants';
import { type CardData } from '@/lib/api';

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
    .toSorted((a, b) => a.rank - b.rank)
    .slice(0, RECOMMENDATIONS_DISPLAY_COUNT);

  return (
    <article className="w-full max-w-2xl mx-auto space-y-8">
      {/* Identity header */}
      <header className="text-center space-y-1.5">
        <h1 className="text-3xl font-bold font-display tracking-tight text-gradient-brand">
          {card.display_name}
        </h1>
        <p className="text-content-secondary text-sm tracking-wide">
          @{card.username}
        </p>
      </header>

      {/* Before / After comparison */}
      <section
        aria-label="Before and after comparison"
        className="grid grid-cols-2 gap-4"
      >
        {/* Before image */}
        <div className="relative rounded-3xl overflow-hidden aspect-[3/4] bg-surface-elevated">
          {/* Subtle desaturating veil */}
          <div
            className="absolute inset-0 z-10 bg-gradient-to-t from-surface-page/80 via-before-900/35 to-transparent"
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
          <span className="absolute bottom-3 left-3 z-20 text-[11px] font-semibold text-content-secondary/80 uppercase tracking-widest">
            Before
          </span>
        </div>

        {/* After image — the hero */}
        <div className="relative rounded-3xl overflow-hidden aspect-[3/4] bg-surface-elevated glow-shadow-after">
          <Image
            src={card.after_image_url}
            alt={`${card.display_name} after glow-up`}
            fill
            className="object-cover"
            sizes="(max-width: 640px) 47vw, 280px"
            priority
          />
          {/* Subtle gradient border via ring */}
          <div
            className="absolute inset-0 z-20 rounded-3xl ring-1 ring-after-500/20"
            aria-hidden="true"
          />
          {/* Bottom gradient for label legibility */}
          <div
            className="absolute inset-x-0 bottom-0 h-16 z-10 bg-gradient-to-t from-black/50 to-transparent"
            aria-hidden="true"
          />
          <span className="absolute bottom-3 left-3 z-30 text-[11px] font-semibold text-after-300 uppercase tracking-widest">
            After
          </span>
        </div>
      </section>

      {/* Engagement counts */}
      <div
        className="flex items-center justify-center gap-6 text-sm"
        aria-label="Engagement stats"
      >
        <span className="flex items-center gap-1.5">
          <svg
            className="w-4 h-4 text-after-400"
            viewBox="0 0 24 24"
            fill="currentColor"
            aria-hidden="true"
          >
            <path d="M11.645 20.91l-.007-.003-.022-.012a15.247 15.247 0 01-.383-.218 25.18 25.18 0 01-4.244-3.17C4.688 15.36 2.25 12.174 2.25 8.25 2.25 5.322 4.714 3 7.688 3A5.5 5.5 0 0112 5.052 5.5 5.5 0 0116.313 3c2.973 0 5.437 2.322 5.437 5.25 0 3.925-2.438 7.111-4.739 9.256a25.175 25.175 0 01-4.244 3.17 15.247 15.247 0 01-.383.219l-.022.012-.007.004-.003.001a.752.752 0 01-.704 0l-.003-.001z" />
          </svg>
          <strong className="text-content-primary font-semibold">
            {card.reaction_count}
          </strong>
          <span className="text-content-secondary">reactions</span>
        </span>
        <span className="text-content-disabled" aria-hidden="true">
          /
        </span>
        <span className="flex items-center gap-1.5">
          <svg
            className="w-4 h-4 text-content-secondary"
            viewBox="0 0 24 24"
            fill="currentColor"
            aria-hidden="true"
          >
            <path
              fillRule="evenodd"
              d="M4.804 21.644A6.707 6.707 0 006 21.75a6.721 6.721 0 003.583-1.029c.774.182 1.584.279 2.417.279 5.322 0 9.75-3.97 9.75-8.5S17.322 4 12 4s-9.75 3.97-9.75 8.5c0 2.012.738 3.87 1.985 5.365-.034.29-.126.733-.319 1.217a9.552 9.552 0 01-.424.849l-.007.012-.002.004a.5.5 0 00.5.726 6.7 6.7 0 001.82-.508z"
              clipRule="evenodd"
            />
          </svg>
          <strong className="text-content-primary font-semibold">
            {card.comment_count}
          </strong>
          <span className="text-content-secondary">comments</span>
        </span>
      </div>

      {/* Improvement recommendations */}
      {topRecommendations.length > 0 && (
        <section aria-labelledby="recommendations-heading" className="space-y-4">
          <h2
            id="recommendations-heading"
            className="text-sm font-semibold font-display text-content-secondary uppercase tracking-wider"
          >
            Top improvements
          </h2>
          <ol className="space-y-3">
            {topRecommendations.map((rec, index) => (
              <li
                key={rec.rank}
                className="flex gap-4 p-4 rounded-2xl glass-card transition-colors duration-200 hover:bg-white/[0.04]"
              >
                <span
                  className="shrink-0 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold bg-after-500/10 text-after-400 ring-1 ring-after-500/20"
                  aria-label={`Rank ${rec.rank}`}
                  style={{ animationDelay: `${index * 100}ms` }}
                >
                  {rec.rank}
                </span>
                <div className="min-w-0">
                  <p className="text-[11px] font-semibold text-after-400/80 uppercase tracking-wider mb-1">
                    {rec.category}
                  </p>
                  <p className="text-sm text-content-primary/90 leading-relaxed">
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
