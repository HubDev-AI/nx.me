import type { Metadata, Viewport } from 'next';

import './globals.css';
import { SITE_NAME, SITE_URL } from '@/config/constants';

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: `${SITE_NAME} — Your Style, Elevated`,
    template: `%s | ${SITE_NAME}`,
  },
  description:
    'See real glow-up transformations and get your own personalised style recommendations with NXME.',
  openGraph: {
    siteName: SITE_NAME,
    type: 'website',
    locale: 'en_US',
  },
  twitter: {
    card: 'summary_large_image',
  },
  robots: {
    index: true,
    follow: true,
  },
};

export const viewport: Viewport = {
  themeColor: '#080808',
  width: 'device-width',
  initialScale: 1,
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  );
}
