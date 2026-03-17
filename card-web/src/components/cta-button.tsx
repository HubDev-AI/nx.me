'use client';

import { useEffect, useState } from 'react';

import { detectPlatform } from '@/lib/user-agent';
import {
  APP_STORE_URL,
  PLAY_STORE_URL,
  APP_BASE_URL,
  APP_DEEP_LINK_PATH,
} from '@/config/constants';

interface CtaButtonProps {
  /** Username — used to build the deep-link with card context */
  username: string;
}

/**
 * CTA button with Universal Link / app-store fallback strategy.
 *
 * Resolution order:
 * 1. iOS → App Store link
 * 2. Android → Play Store link
 * 3. Desktop → Universal Link that opens the app if installed,
 *    otherwise falls back to the marketing/download page
 *
 * The href is resolved on the client after mount to avoid SSR/hydration
 * mismatch (navigator is not available server-side).
 */
export function CtaButton({ username }: CtaButtonProps) {
  const [href, setHref] = useState<string>(APP_STORE_URL);
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    const platform = detectPlatform();

    if (platform === 'ios') {
      setHref(APP_STORE_URL);
    } else if (platform === 'android') {
      setHref(PLAY_STORE_URL);
    } else {
      // Desktop: Universal Link — opens app if installed, web fallback otherwise
      const params = new URLSearchParams({ card: username });
      setHref(`${APP_BASE_URL}${APP_DEEP_LINK_PATH}?${params.toString()}`);
    }

    setMounted(true);
  }, [username]);

  return (
    <a
      href={href}
      target="_blank"
      rel="noopener noreferrer"
      aria-label="Get Your Free Glow-Up — open app or download"
      className={[
        'block w-full text-center py-4 px-6 rounded-2xl',
        'text-base font-bold tracking-wide text-white',
        'bg-after-500 hover:bg-after-600 active:bg-after-700',
        'transition-colors duration-150',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-after-400 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-page',
        // Prevent layout shift while JS hydrates
        !mounted ? 'opacity-0 pointer-events-none' : 'opacity-100',
      ].join(' ')}
    >
      Get Your Free Glow-Up &rarr;
    </a>
  );
}
