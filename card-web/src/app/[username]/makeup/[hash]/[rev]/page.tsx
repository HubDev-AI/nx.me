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
import { getMakeupCardData } from '@/lib/api';

export const revalidate = CARD_REVALIDATE_SECONDS;

interface PageProps {
  params: Promise<{ username: string; hash: string; rev: string }>;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { username, hash, rev } = await params;
  const card = await getMakeupCardData(username, hash, rev);

  if (!card) {
    return { title: 'Card not found' };
  }

  const title = `${card.display_name}'s Makeup Look | ${SITE_NAME}`;
  const description = `See ${card.display_name}'s before & after makeup transformation on NXME.`;
  const cardUrl = `${SITE_URL}/${card.username}/makeup/${card.share_hash}/${card.publish_rev}`;

  const indexable = card.public_index_opt_in;

  return {
    title,
    description,
    robots: {
      index: indexable,
      follow: indexable,
    },
    alternates: {
      canonical: cardUrl,
    },
    openGraph: {
      title,
      description,
      url: cardUrl,
      type: 'website',
      images: [
        {
          url: card.after_image_url,
          width: 1200,
          height: 630,
          alt: `${card.display_name}'s makeup transformation`,
        },
      ],
    },
    twitter: {
      card: 'summary_large_image',
      title,
      description,
      images: [card.after_image_url],
    },
  };
}

export default async function MakeupPage({ params }: PageProps) {
  const { username, hash, rev } = await params;
  const card = await getMakeupCardData(username, hash, rev);

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
    url: `${SITE_URL}/${card.username}/makeup/${card.share_hash}/${card.publish_rev}`,
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
        <CardView card={card} kind="makeup" />

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
