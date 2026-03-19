import { ImageResponse } from 'next/og';

import {
  OG_IMAGE_WIDTH,
  OG_IMAGE_HEIGHT,
  SITE_NAME,
  CARD_REVALIDATE_SECONDS,
} from '@/config/constants';
import { getCardData } from '@/lib/api';

const ALLOWED_IMAGE_HOSTS = ["supabase.co", "fal.ai", "fal.media", "fal.run"];

function isAllowedImageUrl(url: string): boolean {
  try {
    const hostname = new URL(url).hostname;
    return ALLOWED_IMAGE_HOSTS.some(
      (h) => hostname === h || hostname.endsWith(`.${h}`)
    );
  } catch {
    return false;
  }
}

function sanitizeImageUrl(url: string): string {
  return isAllowedImageUrl(url) ? url : "";
}

/** Colors for OG image generation — mirrors design tokens but inline for Satori. */
const OG = {
  BG: '#080808',
  TEXT_PRIMARY: '#F8F8F8',
  TEXT_SECONDARY: '#A0A0A0',
  ACCENT: '#F43F5E',
  GLOW: '#FF8C42',
  BORDER: '#2A2A2A',
  BEFORE_LABEL: '#94A3B8',
  AFTER_LABEL: '#FB7091',
  GLOW_RING: 'rgba(255, 140, 66, 0.40)',
} as const;

export const runtime = 'edge';

export const alt = 'NXME Glow-Up Card';
export const size = { width: OG_IMAGE_WIDTH, height: OG_IMAGE_HEIGHT };
export const contentType = 'image/png';
export const revalidate = CARD_REVALIDATE_SECONDS;

interface Props {
  params: Promise<{ username: string }>;
}

/**
 * Dynamic OG image (1200×630) for the card page.
 *
 * Renders a before/after composite using Satori (Next.js ImageResponse).
 * Falls back gracefully when card data is unavailable.
 *
 * NOTE: Uses Edge runtime — keep imports minimal and avoid Node-only APIs.
 */
export default async function OgImage({ params }: Props) {
  const { username } = await params;
  const card = await getCardData(username);

  // Fallback OG image when card not found
  if (!card) {
    return new ImageResponse(
      (
        <div
          style={{
            width: OG_IMAGE_WIDTH,
            height: OG_IMAGE_HEIGHT,
            background: OG.BG,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexDirection: 'column',
            gap: 16,
          }}
        >
          <div
            style={{
              fontSize: 64,
              fontWeight: 800,
              color: OG.ACCENT,
              letterSpacing: '-2px',
            }}
          >
            {SITE_NAME}
          </div>
          <div style={{ fontSize: 24, color: OG.TEXT_SECONDARY }}>
            Your style, elevated.
          </div>
        </div>
      ),
      { width: OG_IMAGE_WIDTH, height: OG_IMAGE_HEIGHT },
    );
  }

  // Card found — render before/after side-by-side composite
  return new ImageResponse(
    (
      <div
        style={{
          width: OG_IMAGE_WIDTH,
          height: OG_IMAGE_HEIGHT,
          background: OG.BG,
          display: 'flex',
          flexDirection: 'column',
          padding: 40,
          gap: 24,
        }}
      >
        {/* Top: branding */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <div
            style={{
              fontSize: 28,
              fontWeight: 800,
              color: OG.ACCENT,
              letterSpacing: '-1px',
            }}
          >
            {SITE_NAME}
          </div>
          <div style={{ fontSize: 18, color: OG.TEXT_SECONDARY }}>
            @{card.username}&apos;s Glow-Up
          </div>
        </div>

        {/* Middle: image pair */}
        <div
          style={{
            display: 'flex',
            flex: 1,
            gap: 24,
          }}
        >
          {/* Before */}
          <div
            style={{
              flex: 1,
              position: 'relative',
              borderRadius: 16,
              overflow: 'hidden',
              display: 'flex',
            }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={sanitizeImageUrl(card.before_image_url)}
              alt="Before"
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'cover',
                filter: 'grayscale(40%)',
              }}
            />
            <div
              style={{
                position: 'absolute',
                bottom: 12,
                left: 16,
                fontSize: 14,
                fontWeight: 700,
                color: OG.BEFORE_LABEL,
                textTransform: 'uppercase',
                letterSpacing: '2px',
              }}
            >
              Before
            </div>
          </div>

          {/* After */}
          <div
            style={{
              flex: 1,
              position: 'relative',
              borderRadius: 16,
              overflow: 'hidden',
              border: `2px solid ${OG.GLOW_RING}`,
              display: 'flex',
            }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={sanitizeImageUrl(card.after_image_url)}
              alt="After"
              style={{
                width: '100%',
                height: '100%',
                objectFit: 'cover',
              }}
            />
            <div
              style={{
                position: 'absolute',
                bottom: 12,
                left: 16,
                fontSize: 14,
                fontWeight: 700,
                color: OG.AFTER_LABEL,
                textTransform: 'uppercase',
                letterSpacing: '2px',
              }}
            >
              After
            </div>
          </div>
        </div>

        {/* Bottom: CTA strip */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <div style={{ fontSize: 16, color: OG.TEXT_PRIMARY, fontWeight: 600 }}>
            {card.display_name}&apos;s transformation
          </div>
          <div
            style={{
              fontSize: 14,
              color: OG.TEXT_PRIMARY,
              background: OG.ACCENT,
              padding: '8px 20px',
              borderRadius: 24,
              fontWeight: 700,
            }}
          >
            Get Your Free Glow-Up →
          </div>
        </div>
      </div>
    ),
    { width: OG_IMAGE_WIDTH, height: OG_IMAGE_HEIGHT },
  );
}
