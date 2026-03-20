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
  params: Promise<{ username: string; hash: string }>;
}

export async function generateMetadata({
  params,
}: PageProps): Promise<Metadata> {
  const { username, hash } = await params;
  const card = await getCardData(username, hash);

  if (!card) {
    return {
      title: 'Card not found',
    };
  }

  const title = `${card.display_name}'s Glow-Up | ${SITE_NAME}`;
  const description = `See ${card.display_name}'s before & after glow-up transformation on NXME — ${card.recommendations.length} personalised style improvements.`;
  const cardUrl = `${SITE_URL}/${card.username}/glow-up/${card.share_hash}`;

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
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: [card.after_image_url],
    },
  };
}

export default async function GlowUpPage({ params }: PageProps) {
  const { username, hash } = await params;
  const card = await getCardData(username, hash);

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
    url: `${SITE_URL}/${card.username}/glow-up/${card.share_hash}`,
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
