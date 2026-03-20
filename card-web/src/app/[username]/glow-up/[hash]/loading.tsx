import { RECOMMENDATIONS_DISPLAY_COUNT } from '@/config/constants';

/**
 * Streaming loading skeleton for the card page.
 * Shown by Next.js while the async Server Component resolves.
 */
export default function CardLoading() {
  return (
    <main className="min-h-screen bg-[#0a0a0a] py-16 px-6 sm:px-12">
      <div className="max-w-2xl mx-auto animate-pulse">
        {/* Header skeleton */}
        <div className="text-center mb-10">
          <div className="h-10 w-48 bg-[#181818] rounded-lg mx-auto" />
          <div className="h-4 w-28 bg-[#141414] rounded mt-3 mx-auto" />
        </div>

        {/* Before/After image skeletons */}
        <div className="grid grid-cols-2 gap-3 sm:gap-4">
          <div className="aspect-[3/4] rounded-xl bg-[#181818]" />
          <div className="aspect-[3/4] rounded-xl bg-[#181818]" />
        </div>

        {/* Counts skeleton */}
        <div className="flex justify-center gap-6 mt-8">
          <div className="h-4 w-24 bg-[#141414] rounded" />
          <div className="h-4 w-24 bg-[#141414] rounded" />
        </div>

        {/* Recommendations skeleton */}
        <div className="mt-12">
          <div className="h-3 w-36 bg-[#141414] rounded mb-8" />
          <div className="space-y-0">
            {Array.from({ length: RECOMMENDATIONS_DISPLAY_COUNT }).map((_, i) => (
              <div
                key={i}
                className={[
                  'flex gap-4 py-5',
                  i > 0 ? 'border-t border-white/[0.06]' : '',
                ].join(' ')}
              >
                <div className="shrink-0 w-7 h-7 rounded-full bg-[#181818]" />
                <div className="flex-1 space-y-2">
                  <div className="h-3 w-16 bg-[#181818] rounded" />
                  <div className="h-4 w-full bg-[#141414] rounded" />
                </div>
              </div>
            ))}
          </div>
        </div>

        {/* CTA skeleton */}
        <div className="mt-12">
          <div className="h-12 rounded-full bg-[#181818]" />
        </div>
      </div>
    </main>
  );
}
