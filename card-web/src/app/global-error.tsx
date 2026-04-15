'use client';

import { useEffect } from 'react';

import { DEFAULT_ACCENT } from '@/config/constants';

interface GlobalErrorProps {
  error: Error & { digest?: string };
  reset: () => void;
}

/**
 * Global error boundary for the entire application.
 *
 * Next.js App Router requires global-error.tsx to include its own <html>
 * and <body> tags because it replaces the root layout when triggered.
 * The segment-level error.tsx (without the HTML shell) handles errors
 * within nested route segments.
 */
export default function GlobalError({ error, reset }: GlobalErrorProps) {
  useEffect(() => {
    if (process.env.NODE_ENV !== 'production') {
      // eslint-disable-next-line no-console
      console.error(error);
    }
  }, [error]);

  return (
    <html lang="en">
      <body style={{ margin: 0, backgroundColor: '#080808', color: '#F8F8F8' }}>
        <main
          style={{
            display: 'flex',
            flexDirection: 'column',
            alignItems: 'center',
            justifyContent: 'center',
            minHeight: '100vh',
            padding: '0 24px',
            textAlign: 'center',
            fontFamily: 'system-ui, -apple-system, sans-serif',
          }}
        >
          <h1 style={{ fontSize: '20px', fontWeight: 700, marginBottom: '8px' }}>
            Something went wrong
          </h1>
          <p style={{ fontSize: '14px', color: '#A0A0A0', maxWidth: '320px', marginBottom: '24px' }}>
            An unexpected error occurred. Please try again.
          </p>
          <button
            onClick={reset}
            style={{
              padding: '12px 24px',
              borderRadius: '12px',
              backgroundColor: DEFAULT_ACCENT,
              color: '#FFFFFF',
              fontSize: '14px',
              fontWeight: 600,
              border: 'none',
              cursor: 'pointer',
            }}
          >
            Try again
          </button>
        </main>
      </body>
    </html>
  );
}
