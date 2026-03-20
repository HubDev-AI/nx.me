import { CardNotFound } from '@/components/card-not-found';

/** Root-level not found page */
export default function NotFound() {
  return (
    <main className="min-h-screen bg-[#0a0a0a] px-6">
      <div className="max-w-2xl mx-auto">
        <CardNotFound />
      </div>
    </main>
  );
}
