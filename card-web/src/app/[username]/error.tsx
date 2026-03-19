'use client';

import { useEffect } from 'react';

interface ErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

/**
 * Segment-level error boundary for the [username] card route.
 * Catches errors during rendering without affecting the rest of the app.
 */
export default function CardError({ error, reset }: ErrorProps) {
  useEffect(() => {
    // Log full error details only in non-production environments
    if (process.env.NODE_ENV !== "production") {
      // eslint-disable-next-line no-console
      console.error(error);
    }
  }, [error]);

  return (
    <main className="relative flex flex-col items-center justify-center min-h-screen px-6 text-center space-y-5 bg-surface-page overflow-hidden">
      <div
        className="ambient-orb w-[300px] h-[300px] bg-after-500/[0.05] top-1/3 left-1/2 -translate-x-1/2 -translate-y-1/2"
        aria-hidden="true"
      />
      <div className="relative z-10 space-y-5">
        <div className="w-14 h-14 rounded-full flex items-center justify-center bg-after-500/10 ring-1 ring-after-500/20 mx-auto">
          <svg
            className="w-6 h-6 text-after-400"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth={1.5}
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M12 9v3.75m-9.303 3.376c-.866 1.5.217 3.374 1.948 3.374h14.71c1.73 0 2.813-1.874 1.948-3.374L13.949 3.378c-.866-1.5-3.032-1.5-3.898 0L2.697 16.126zM12 15.75h.007v.008H12v-.008z" />
          </svg>
        </div>
        <div className="space-y-2">
          <h1 className="text-xl font-bold font-display text-content-primary">
            Something went wrong
          </h1>
          <p className="text-content-secondary text-sm max-w-xs">
            We couldn&apos;t load this card. Please try again.
          </p>
        </div>
        <button
          onClick={reset}
          className={[
            'px-6 py-3 rounded-xl',
            'bg-gradient-to-r from-after-600 via-after-500 to-glow',
            'text-white text-sm font-semibold font-display',
            'glow-shadow-cta',
            'transition-all duration-200',
            'hover:scale-[1.02] active:scale-[0.98]',
            'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-after-400 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-page',
          ].join(' ')}
        >
          Try again
        </button>
      </div>
    </main>
  );
}
