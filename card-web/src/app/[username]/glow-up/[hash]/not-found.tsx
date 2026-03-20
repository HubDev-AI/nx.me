import { CardNotFound } from '@/components/card-not-found';

/**
 * Rendered by Next.js when `notFound()` is called from the card page.
 * Also shown for HTTP 410 (deleted card) — getCardData returns null for both.
 */
export default function CardNotFoundPage() {
  return (
    <main className="min-h-screen bg-[#0a0a0a] px-6">
      <div className="max-w-2xl mx-auto">
        <CardNotFound />
      </div>
    </main>
  );
}
