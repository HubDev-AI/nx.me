import Link from 'next/link';

import { APP_BASE_URL } from '@/config/constants';

/**
 * Rendered when a card has been deleted (HTTP 410) or simply never existed.
 */
export function CardNotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-6 space-y-5">
      {/* Search/sparkle icon — SVG, not emoji */}
      <div className="w-14 h-14 rounded-full flex items-center justify-center bg-after-500/10 ring-1 ring-after-500/20">
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
          <path d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
        </svg>
      </div>
      <div className="space-y-2">
        <h1 className="text-xl font-bold font-display text-content-primary">
          Card not found
        </h1>
        <p className="text-content-secondary text-sm max-w-xs">
          This glow-up card may have been removed or the link might be incorrect.
        </p>
      </div>
      <Link
        href={APP_BASE_URL}
        target="_blank"
        rel="noopener noreferrer"
        className={[
          'inline-block px-6 py-3 rounded-xl',
          'bg-gradient-to-r from-after-600 via-after-500 to-glow',
          'text-white text-sm font-semibold font-display',
          'glow-shadow-cta',
          'transition-all duration-200',
          'hover:scale-[1.02] active:scale-[0.98]',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-after-400 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-page',
        ].join(' ')}
      >
        Get NXME &rarr;
      </Link>
    </div>
  );
}
