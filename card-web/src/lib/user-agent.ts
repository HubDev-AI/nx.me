/**
 * User-agent detection utilities.
 * These run in the browser (client components only).
 */

export type DevicePlatform = 'ios' | 'android' | 'desktop';

/**
 * Detects the current device platform based on navigator.userAgent.
 * Safe to call only from client components.
 */
export function detectPlatform(): DevicePlatform {
  if (typeof navigator === 'undefined') return 'desktop';

  const ua = navigator.userAgent;

  if (/iPad|iPhone|iPod/.test(ua)) return 'ios';
  // iPadOS 13+ sends a desktop Macintosh user-agent; detect via touch support
  if (/Macintosh/.test(ua) && navigator.maxTouchPoints > 0) return 'ios';
  if (/Android/.test(ua)) return 'android';
  return 'desktop';
}
