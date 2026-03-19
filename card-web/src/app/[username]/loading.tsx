import { RECOMMENDATIONS_DISPLAY_COUNT } from '@/config/constants';

/**
 * Streaming loading skeleton for the card page.
 * Shown by Next.js while the async Server Component resolves.
 */
export default function CardLoading() {
  return (
    <main className="relative min-h-screen bg-surface-page py-12 px-4 overflow-hidden">
      {/* Ambient background — matches card page */}
      <div
        className="ambient-orb w-[500px] h-[500px] bg-after-500/[0.06] -top-60 left-1/2 -translate-x-1/2"
        aria-hidden="true"
      />

      <div className="relative z-10 max-w-2xl mx-auto space-y-10 animate-pulse">
        {/* Header skeleton */}
        <div className="text-center space-y-2">
          <div className="h-8 w-44 bg-surface-elevated rounded-lg mx-auto" />
          <div className="h-4 w-28 bg-surface-elevated/60 rounded mx-auto" />
        </div>

        {/* Before/After image skeletons */}
        <div className="grid grid-cols-2 gap-4">
          <div className="aspect-[3/4] rounded-3xl bg-surface-elevated" />
          <div className="aspect-[3/4] rounded-3xl bg-surface-elevated ring-1 ring-after-500/10" />
        </div>

        {/* Counts skeleton */}
        <div className="flex justify-center gap-6">
          <div className="h-4 w-24 bg-surface-elevated/60 rounded" />
          <div className="h-4 w-24 bg-surface-elevated/60 rounded" />
        </div>

        {/* Recommendations skeleton */}
        <div className="space-y-4">
          <div className="h-4 w-36 bg-surface-elevated/60 rounded" />
          <div className="space-y-3">
            {Array.from({ length: RECOMMENDATIONS_DISPLAY_COUNT }).map((_, i) => (
              <div
                key={i}
                className="h-[72px] rounded-2xl glass-card"
              />
            ))}
          </div>
        </div>

        {/* CTA skeleton */}
        <div className="px-2">
          <div className="h-14 rounded-2xl bg-surface-elevated" />
        </div>
      </div>
    </main>
  );
}
