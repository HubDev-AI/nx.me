import type { Metadata } from 'next';
import { notFound } from 'next/navigation';

import { CardView } from '@/components/card-view';
import { CtaButton } from '@/components/cta-button';
import {
  CARD_REVALIDATE_SECONDS,
  SITE_NAME,
  SITE_URL,
} from '@/config/constants';
import { getCardData } from '@/lib/api';

/** ISR: revalidate the page at most every 60 seconds */
export const revalidate = CARD_REVALIDATE_SECONDS;

interface PageProps {
  params: Promise<{ username: string }>;
}

export async function generateMetadata({
  params,
}: PageProps): Promise<Metadata> {
  const { username } = await params;
  const card = await getCardData(username);

  if (!card) {
    return {
      title: 'Card not found',
    };
  }

  const title = `${card.display_name}'s Glow-Up | ${SITE_NAME}`;
  const description = `See ${card.display_name}'s before & after glow-up transformation on NXME — ${card.recommendations.length} personalised style improvements.`;
  const cardUrl = `${SITE_URL}/${card.username}`;

  return {
    title,
    description,
    alternates: {
      canonical: cardUrl,
    },
    openGraph: {
      title,
      description,
      url: cardUrl,
      type: 'website',
      // images intentionally omitted — Next.js auto-wires opengraph-image.tsx
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: [card.after_image_url],
    },
  };
}

/**
 * Card page — SSG with ISR.
 *
 * Fetches public card data from the backend and renders:
 * - Before/after image comparison
 * - Top 5 personalised recommendations
 * - App download CTA (platform-aware, resolved client-side)
 */
export default async function CardPage({ params }: PageProps) {
  const { username } = await params;
  // Next.js automatically deduplicates this fetch with the one in generateMetadata
  const card = await getCardData(username);

  if (!card) {
    notFound();
  }

  const jsonLd = {
    '@context': 'https://schema.org',
    '@type': 'Person',
    name: card.display_name,
    image: {
      '@type': 'ImageObject',
      url: card.after_image_url,
    },
    url: `${SITE_URL}/${card.username}`,
  };

  return (
    <main className="relative min-h-screen bg-surface-page py-12 px-4 overflow-hidden">
      {/* Ambient background effects */}
      <div
        className="ambient-orb w-[500px] h-[500px] bg-after-500/[0.06] -top-60 left-1/2 -translate-x-1/2"
        aria-hidden="true"
      />
      <div
        className="ambient-orb w-[300px] h-[300px] bg-glow/[0.04] bottom-20 -right-20"
        aria-hidden="true"
      />

      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(jsonLd).replace(/</g, '\\u003c'),
        }}
      />

      <div className="relative z-10 max-w-2xl mx-auto space-y-10">
        <CardView card={card} />

        <div className="px-2">
          <CtaButton username={card.username} />
        </div>

        <footer className="text-center text-xs text-content-disabled pb-4">
          Powered by{' '}
          <span className="text-gradient-brand font-semibold font-display">
            {SITE_NAME}
          </span>
        </footer>
      </div>
    </main>
  );
}
