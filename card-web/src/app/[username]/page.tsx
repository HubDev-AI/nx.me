import type { Metadata } from 'next';
import { notFound } from 'next/navigation';

import { CardView } from '@/components/card-view';
import { CtaButton } from '@/components/cta-button';
import { buildTheme } from '@/components/theme-provider';
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

  const t = buildTheme();

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
    <main
      className="min-h-screen bg-[#0a0a0a] text-[#e8e8e8] py-16 px-6 sm:px-12"
      style={{ '--accent': t.accent } as React.CSSProperties}
    >
      <script
        type="application/ld+json"
        dangerouslySetInnerHTML={{
          __html: JSON.stringify(jsonLd).replace(/</g, '\\u003c'),
        }}
      />

      <div className="max-w-2xl mx-auto">
        <CardView card={card} />

        <div className="mt-12">
          <CtaButton username={card.username} />
        </div>

        <footer className="mt-16 section-rule pt-6 text-center text-xs text-[#444]">
          Powered by{' '}
          <span className="font-display text-white/60">{SITE_NAME}</span>
        </footer>
      </div>
    </main>
  );
}
