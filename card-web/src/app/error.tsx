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
    <main className="flex flex-col items-center justify-center min-h-screen px-6 text-center bg-[#0a0a0a]">
      <div className="space-y-6">
        <div className="w-12 h-12 rounded-full flex items-center justify-center bg-[#181818] mx-auto">
          <svg
            className="w-5 h-5 text-[#555]"
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
          <h1 className="font-display text-2xl text-white">
            Something went wrong
          </h1>
          <p className="text-[#888] text-sm max-w-xs leading-relaxed">
            We couldn&apos;t load this card. Please try again.
          </p>
        </div>
        <button
          onClick={reset}
          className="inline-flex items-center gap-2 text-[#0a0a0a] text-sm font-medium px-7 py-3.5 rounded-full transition-opacity hover:opacity-85 active:opacity-70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/20 focus-visible:ring-offset-2 focus-visible:ring-offset-[#0a0a0a]"
          style={{ backgroundColor: 'var(--accent, #F43F5E)' }}
        >
          Try again
        </button>
      </div>
    </main>
  );
}
