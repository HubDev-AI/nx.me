import { RECOMMENDATIONS_DISPLAY_COUNT } from '@/config/constants';

/**
 * Streaming loading skeleton for the card page.
 * Shown by Next.js while the async Server Component resolves.
 */
export default function CardLoading() {
  return (
    <main className="min-h-screen bg-surface-page py-10 px-4">
      <div className="max-w-2xl mx-auto space-y-8 animate-pulse">
        {/* Header skeleton */}
        <div className="text-center space-y-2">
          <div className="h-7 w-40 bg-surface-elevated rounded-lg mx-auto" />
          <div className="h-4 w-24 bg-surface-elevated rounded mx-auto" />
        </div>

        {/* Before/After image skeletons */}
        <div className="grid grid-cols-2 gap-3">
          <div className="aspect-[3/4] rounded-2xl bg-surface-elevated" />
          <div className="aspect-[3/4] rounded-2xl bg-surface-elevated" />
        </div>

        {/* Counts skeleton */}
        <div className="flex justify-center gap-6">
          <div className="h-4 w-24 bg-surface-elevated rounded" />
          <div className="h-4 w-24 bg-surface-elevated rounded" />
        </div>

        {/* Recommendations skeleton */}
        <div className="space-y-3">
          <div className="h-4 w-32 bg-surface-elevated rounded mb-4" />
          {Array.from({ length: RECOMMENDATIONS_DISPLAY_COUNT }).map((_, i) => (
            <div
              key={i}
              className="h-16 rounded-xl bg-surface-card border border-border-default"
            />
          ))}
        </div>

        {/* CTA skeleton */}
        <div className="h-14 rounded-2xl bg-surface-elevated" />
      </div>
    </main>
  );
}
