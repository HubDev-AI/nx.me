import type { Metadata, Viewport } from 'next';
import { Inter, Instrument_Serif } from 'next/font/google';

import './globals.css';
import { SITE_NAME, SITE_URL } from '@/config/constants';

const inter = Inter({
  subsets: ['latin'],
  variable: '--font-inter',
});

const instrumentSerif = Instrument_Serif({
  subsets: ['latin'],
  variable: '--font-display',
  weight: '400',
  style: ['normal', 'italic'],
});

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
    <html lang="en" className={`${inter.variable} ${instrumentSerif.variable}`}>
      <body>{children}</body>
    </html>
  );
}
