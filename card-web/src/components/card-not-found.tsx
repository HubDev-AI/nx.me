import Link from 'next/link';

import { APP_BASE_URL } from '@/config/constants';

/**
 * Rendered when a card has been deleted (HTTP 410) or simply never existed.
 */
export function CardNotFound() {
  return (
    <div className="flex flex-col items-center justify-center min-h-[60vh] text-center px-6 space-y-4">
      <p className="text-4xl" aria-hidden="true">
        ✨
      </p>
      <h1 className="text-xl font-bold text-content-primary">
        Card not found
      </h1>
      <p className="text-content-secondary text-sm max-w-xs">
        This glow-up card may have been removed or the link might be incorrect.
      </p>
      <Link
        href={APP_BASE_URL}
        target="_blank"
        rel="noopener noreferrer"
        className="mt-4 inline-block px-6 py-3 rounded-xl bg-after-500 hover:bg-after-600 text-white text-sm font-semibold transition-colors"
      >
        Get NXME &rarr;
      </Link>
    </div>
  );
}
