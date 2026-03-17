import { CardNotFound } from '@/components/card-not-found';

/** Root-level not found page */
export default function NotFound() {
  return (
    <main className="min-h-screen bg-surface-page px-4">
      <div className="max-w-2xl mx-auto">
        <CardNotFound />
      </div>
    </main>
  );
}
