import { ImageResponse } from 'next/og';

import {
  OG_IMAGE_WIDTH,
  OG_IMAGE_HEIGHT,
  SITE_NAME,
  CARD_REVALIDATE_SECONDS,
} from '@/config/constants';
import { getCardData } from '@/lib/api';

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
            background: '#080808',
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
              color: '#F43F5E',
              letterSpacing: '-2px',
            }}
          >
            {SITE_NAME}
          </div>
          <div style={{ fontSize: 24, color: '#A0A0A0' }}>
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
          background: '#080808',
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
              color: '#F43F5E',
              letterSpacing: '-1px',
            }}
          >
            {SITE_NAME}
          </div>
          <div style={{ fontSize: 18, color: '#A0A0A0' }}>
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
              src={card.before_image_url}
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
                color: '#94A3B8',
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
              border: '2px solid rgba(255, 140, 66, 0.40)',
              display: 'flex',
            }}
          >
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={card.after_image_url}
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
                color: '#FB7091',
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
          <div style={{ fontSize: 16, color: '#F8F8F8', fontWeight: 600 }}>
            {card.display_name}&apos;s transformation
          </div>
          <div
            style={{
              fontSize: 14,
              color: '#F8F8F8',
              background: '#F43F5E',
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
