import type { Metadata } from 'next';
import Link from 'next/link';

import { APP_STORE_URL, PLAY_STORE_URL, SITE_NAME } from '@/config/constants';

export const metadata: Metadata = {
  title: `${SITE_NAME} — Your Style, Elevated`,
  description:
    'Discover your personalised glow-up plan. Real transformations, AI-powered style recommendations.',
};

/**
 * Landing page — shown at the root path.
 * Directs visitors to download the app.
 */
export default function HomePage() {
  return (
    <main className="flex flex-col items-center justify-center min-h-screen px-6 text-center space-y-8">
      <div className="space-y-3">
        <h1 className="text-4xl font-extrabold tracking-tight text-content-primary">
          NXME
        </h1>
        <p className="text-lg text-content-secondary max-w-sm">
          Your style, elevated. Get a personalised glow-up plan powered by AI.
        </p>
      </div>

      <div className="flex flex-col gap-3 w-full max-w-xs">
        <Link
          href={APP_STORE_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="block w-full py-4 px-6 rounded-2xl bg-after-500 hover:bg-after-600 active:bg-after-700 text-white font-bold text-base text-center transition-colors"
        >
          Download on the App Store
        </Link>
        <Link
          href={PLAY_STORE_URL}
          target="_blank"
          rel="noopener noreferrer"
          className="block w-full py-4 px-6 rounded-2xl bg-surface-elevated hover:bg-surface-subtle border border-border-default text-content-primary font-bold text-base text-center transition-colors"
        >
          Get it on Google Play
        </Link>
      </div>
    </main>
  );
}
