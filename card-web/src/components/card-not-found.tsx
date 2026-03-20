import Link from 'next/link';

import { APP_BASE_URL } from '@/config/constants';

/**
 * Rendered when a card has been deleted (HTTP 410) or simply never existed.
 */
export function CardNotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-6 space-y-6">
      {/* Search icon */}
      <div className="w-12 h-12 rounded-full flex items-center justify-center bg-[#181818]">
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
          <path d="M21 21l-5.197-5.197m0 0A7.5 7.5 0 105.196 5.196a7.5 7.5 0 0010.607 10.607z" />
        </svg>
      </div>
      <div className="space-y-2">
        <h1 className="font-display text-2xl text-white">
          Card not found
        </h1>
        <p className="text-[#888] text-sm max-w-xs leading-relaxed">
          This glow-up card may have been removed or the link might be incorrect.
        </p>
      </div>
      <Link
        href={APP_BASE_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="inline-flex items-center gap-2 text-[#0a0a0a] text-sm font-medium px-7 py-3.5 rounded-full transition-opacity hover:opacity-85 active:opacity-70 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white/20 focus-visible:ring-offset-2 focus-visible:ring-offset-[#0a0a0a]"
        style={{ backgroundColor: 'var(--accent, #F43F5E)' }}
      >
        Get NXME &rarr;
      </Link>
    </div>
  );
}
