'use client';

import { useCallback, useEffect, useState } from 'react';

import {
  APP_STORE_URL,
  PLAY_STORE_URL,
  APP_BASE_URL,
  APP_DEEP_LINK_PATH,
  APP_OPEN_TIMEOUT_MS,
} from '@/config/constants';
import { detectPlatform } from '@/lib/user-agent';

interface CtaButtonProps {
  /** Username — used to build the deep-link with card context */
  username: string;
}

/**
 * CTA button with Universal Link / app-store fallback strategy.
 *
 * Resolution order (all platforms):
 * 1. Attempt to open the installed app via Universal Link
 * 2. After APP_OPEN_TIMEOUT_MS with no app switch, redirect to the
 *    platform-appropriate store (iOS → App Store, Android → Play Store,
 *    Desktop → marketing/download page)
 *
 * The platform is resolved on the client after mount to avoid SSR/hydration
 * mismatch (navigator is not available server-side).
 */
export function CtaButton({ username }: CtaButtonProps) {
  const [mounted, setMounted] = useState(false);

  useEffect(() => {
    setMounted(true);
  }, []);

  const handleClick = useCallback(
    (e: React.MouseEvent<HTMLAnchorElement>) => {
      e.preventDefault();

      const platform = detectPlatform();
      const params = new URLSearchParams({ card: username });
      const universalLink = `${APP_BASE_URL}${APP_DEEP_LINK_PATH}?${params.toString()}`;

      const storeUrl =
        platform === 'ios'
          ? APP_STORE_URL
          : platform === 'android'
            ? PLAY_STORE_URL
            : universalLink; // Desktop: universal link is both the app target and the fallback

      // Attempt to open the app via the universal link.
      // If the app is installed, the OS intercepts and opens it; the page stays
      // in the background and the setTimeout never fires a redirect.
      // If the app is not installed, the universal link 404s silently (or the
      // browser ignores it) and we redirect to the store after the timeout.
      window.location.href = universalLink;

      if (platform !== 'desktop') {
        // On mobile: after the app-open window, fall back to the store.
        const timer = setTimeout(() => {
          window.location.href = storeUrl;
        }, APP_OPEN_TIMEOUT_MS);

        // If the user switches back to the browser, clear the pending redirect.
        const clearOnFocus = () => {
          clearTimeout(timer);
          window.removeEventListener('focus', clearOnFocus);
        };
        window.addEventListener('focus', clearOnFocus);
      }
    },
    [username],
  );

  // Build the visible href for right-click / copy-link UX
  const params = new URLSearchParams({ card: username });
  const displayHref = `${APP_BASE_URL}${APP_DEEP_LINK_PATH}?${params.toString()}`;

  return (
    <a
      href={displayHref}
      onClick={mounted ? handleClick : undefined}
      aria-label="Get Your Free Glow-Up — open app or download"
      className={[
        'block w-full text-center py-4 px-6 rounded-2xl',
        'text-base font-bold tracking-wide text-white',
        'bg-after-500 hover:bg-after-600 active:bg-after-700',
        'transition-colors duration-150',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-after-400 focus-visible:ring-offset-2 focus-visible:ring-offset-surface-page',
        // Visible from the start with default href; JS swaps click handler on mount
        'opacity-100',
      ].join(' ')}
    >
      Get Your Free Glow-Up &rarr;
    </a>
  );
}
