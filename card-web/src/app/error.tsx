'use client';

import { useEffect } from 'react';

interface ErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

/**
 * Global error boundary — catches unexpected errors during rendering.
 * Must be a Client Component as per Next.js App Router requirements.
 */
export default function GlobalError({ error, reset }: ErrorProps) {
  useEffect(() => {
    // Log full error details only in non-production environments
    if (process.env.NODE_ENV !== "production") {
      // eslint-disable-next-line no-console
      console.error(error);
    }
  }, [error]);

  return (
    <main className="flex flex-col items-center justify-center min-h-screen px-6 text-center space-y-4 bg-surface-page">
      <h1 className="text-xl font-bold text-content-primary">
        Something went wrong
      </h1>
      <p className="text-content-secondary text-sm max-w-xs">
        We couldn&apos;t load this card. Please try again.
      </p>
      <button
        onClick={reset}
        className="px-6 py-3 rounded-xl bg-after-500 hover:bg-after-600 text-white text-sm font-semibold transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-after-400 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-page"
      >
        Try again
      </button>
    </main>
  );
}
