import type { Metadata } from 'next';
import Link from 'next/link';

import { APP_STORE_URL, PLAY_STORE_URL, SITE_NAME } from '@/config/constants';

export const metadata: Metadata = {
  title: `${SITE_NAME} — Your Style, Elevated`,
  description:
    'Discover your personalised glow-up plan. Real transformations, AI-powered style recommendations.',
};

/** Force dynamic rendering so each visitor gets a random image set */
export const dynamic = 'force-dynamic';

/** 10 before/after portrait pairs from Unsplash (diverse subjects) */
const IMAGE_SETS_COUNT = 10;

function getRandomImageSet() {
  const n = Math.floor(Math.random() * IMAGE_SETS_COUNT) + 1;
  return {
    before: `/images/before-${n}.jpg`,
    after: `/images/after-${n}.jpg`,
  };
}

/**
 * Photography-driven editorial landing page.
 *
 * Image rotation: 10 before/after pairs, randomly selected per request.
 * Features: aligned to generation-spec.md keyword categories
 *   (hair, eyebrows, facial hair, clothing, grooming, lighting).
 */
export default function HomePage() {
  const images = getRandomImageSet();

  return (
    <main className="bg-[#0a0a0a] text-[#e8e8e8]">

      {/* ── HERO ─────────────────────────────────────────────
          Full-bleed portrait. Text bottom-left. Cinematic.
      ─────────────────────────────────────────────────────── */}
      <section className="relative min-h-screen">
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src="/images/hero-portrait.jpg"
          alt=""
          className="absolute inset-0 w-full h-full object-cover object-top"
          role="presentation"
        />
        <div className="absolute inset-0 bg-gradient-to-t from-[#0a0a0a] via-[#0a0a0a]/60 to-transparent" />

        <div className="relative z-10 min-h-screen flex flex-col justify-end px-6 sm:px-12 pb-16 sm:pb-24">
          <p className="animate-enter text-xs tracking-[0.25em] uppercase text-white/40 mb-6">
            {SITE_NAME}
          </p>
          <h1 className="animate-enter animate-enter-delay-1 font-display text-[clamp(3rem,11vw,7.5rem)] leading-[0.9] tracking-[-0.02em] text-white max-w-3xl">
            Your style,
            <br />
            <em className="text-accent">elevated.</em>
          </h1>
          <p className="animate-enter animate-enter-delay-2 mt-6 text-sm sm:text-base text-white/50 max-w-sm leading-relaxed">
            AI-powered style recommendations. See your transformation before you commit.
          </p>
          <div className="animate-enter animate-enter-delay-3 mt-8 flex items-center gap-6">
            <Link
              href={APP_STORE_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 bg-white text-[#0a0a0a] text-sm font-medium px-7 py-3.5 rounded-full transition-opacity hover:opacity-85 active:opacity-70"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.8-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z" />
              </svg>
              Get the app
            </Link>
            <Link
              href={PLAY_STORE_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-white/40 hover:text-white/70 transition-colors underline underline-offset-4 decoration-white/20"
            >
              Android
            </Link>
          </div>
        </div>
      </section>

      {/* ── BEFORE / AFTER ───────────────────────────────────
          Random pair from 10 sets. Different on each visit.
      ─────────────────────────────────────────────────────── */}
      <section className="section-rule">
        <div className="px-6 sm:px-12 py-16 sm:py-24">
          <p className="text-xs tracking-[0.25em] uppercase text-[#555] mb-12">
            The transformation
          </p>
        </div>
        <div className="grid grid-cols-2">
          <div className="relative aspect-[3/4] sm:aspect-[4/5]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={images.before}
              alt="Before: casual everyday look"
              className="absolute inset-0 w-full h-full object-cover grayscale-[30%]"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-[#0a0a0a]/70 to-transparent" />
            <span className="absolute bottom-4 left-4 sm:bottom-6 sm:left-6 text-xs tracking-[0.2em] uppercase text-white/50">
              Before
            </span>
          </div>
          <div className="relative aspect-[3/4] sm:aspect-[4/5]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={images.after}
              alt="After: styled and confident"
              className="absolute inset-0 w-full h-full object-cover"
            />
            <div className="absolute inset-0 bg-gradient-to-t from-[#0a0a0a]/70 to-transparent" />
            <span className="absolute bottom-4 left-4 sm:bottom-6 sm:left-6 text-xs tracking-[0.2em] uppercase text-accent">
              After
            </span>
          </div>
        </div>
        <div className="px-6 sm:px-12 py-16 sm:py-24">
          <p className="font-display text-2xl sm:text-4xl text-white leading-snug max-w-2xl">
            Same person. Different presence.
            <br />
            <em className="text-white/40">That&apos;s what a glow-up looks like.</em>
          </p>
        </div>
      </section>

      {/* ── MANIFESTO ──────────────────────────────────────── */}
      <section className="section-rule px-6 sm:px-12 py-24 sm:py-40">
        <div className="max-w-4xl">
          <p className="font-display text-[clamp(1.5rem,4.5vw,3.2rem)] leading-[1.15] text-white">
            We don&apos;t smooth your skin.
            <br />
            We don&apos;t change your face.
            <br />
            <em className="text-accent">We show you what your style could be.</em>
          </p>
        </div>
      </section>

      {/* ── WHAT WE ANALYSE ──────────────────────────────────
          Real categories from generation-spec.md keyword allowlist:
          Hair (30), Eyebrows (8), Facial hair (7), Clothing (10),
          Grooming (3), Lighting (8). Priority: hair > grooming >
          eyebrows > facial_hair > clothing > lighting.
          Showing the top 3 image-friendly categories with photos.
      ─────────────────────────────────────────────────────── */}
      <section className="section-rule">
        <div className="px-6 sm:px-12 py-16 sm:py-24">
          <p className="text-xs tracking-[0.25em] uppercase text-[#555]">
            What we analyse
          </p>
        </div>

        {/* Hair — the #1 glow-up category (30 keywords) */}
        <div className="grid sm:grid-cols-2">
          <div className="relative aspect-[4/3]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/images/detail-hair.jpg"
              alt="Hair styling"
              className="absolute inset-0 w-full h-full object-cover"
            />
          </div>
          <div className="flex items-center px-6 sm:px-12 py-12 sm:py-0">
            <div>
              <h3 className="font-display text-3xl sm:text-4xl text-white">Hair</h3>
              <p className="mt-4 text-sm text-[#888] leading-relaxed max-w-sm">
                Cut, texture, colour, styling. From textured crops to soft waves — 30 styling options matched to your face shape.
              </p>
            </div>
          </div>
        </div>

        {/* Clothing — reversed layout */}
        <div className="grid sm:grid-cols-2">
          <div className="flex items-center px-6 sm:px-12 py-12 sm:py-0 order-2 sm:order-1">
            <div>
              <h3 className="font-display text-3xl sm:text-4xl text-white">Clothing</h3>
              <p className="mt-4 text-sm text-[#888] leading-relaxed max-w-sm">
                Fitted blazers, leather jackets, smart casual, streetwear. The right silhouette changes everything.
              </p>
            </div>
          </div>
          <div className="relative aspect-[4/3] order-1 sm:order-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/images/detail-accessories.jpg"
              alt="Style and clothing details"
              className="absolute inset-0 w-full h-full object-cover"
            />
          </div>
        </div>

        {/* Grooming + facial hair + eyebrows */}
        <div className="grid sm:grid-cols-2">
          <div className="relative aspect-[4/3]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src="/images/detail-grooming.jpg"
              alt="Grooming and skincare"
              className="absolute inset-0 w-full h-full object-cover"
            />
          </div>
          <div className="flex items-center px-6 sm:px-12 py-12 sm:py-0">
            <div>
              <h3 className="font-display text-3xl sm:text-4xl text-white">Grooming</h3>
              <p className="mt-4 text-sm text-[#888] leading-relaxed max-w-sm">
                Brows, facial hair, skin health. Plus lighting that makes everything look better.
              </p>
            </div>
          </div>
        </div>

        {/* Full category list as text — all 7 real categories */}
        <div className="px-6 sm:px-12 py-16 sm:py-24">
          <p className="text-xs tracking-[0.25em] uppercase text-[#555] mb-8">
            All categories
          </p>
          <div className="flex flex-wrap gap-3">
            {['Hair', 'Eyebrows', 'Facial hair', 'Clothing', 'Accessories', 'Grooming', 'Lighting'].map((cat) => (
              <span
                key={cat}
                className="px-4 py-2 text-xs tracking-wide text-[#888] border border-[#222] rounded-full"
              >
                {cat}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* ── HOW IT WORKS ─────────────────────────────────── */}
      <section className="section-rule px-6 sm:px-12 py-24 sm:py-40">
        <div className="max-w-5xl">
          <p className="text-xs tracking-[0.25em] uppercase text-[#555] mb-20">
            How it works
          </p>

          <div className="space-y-16 sm:space-y-20">
            {[
              { n: '01', title: 'Upload a selfie', desc: 'One photo. No angles, no filters. Just you.' },
              { n: '02', title: 'Get your analysis', desc: 'AI evaluates hair, grooming, clothing, and more — ranked by impact.' },
              { n: '03', title: 'See the glow-up', desc: 'A before & after card with personalised recommendations you can share.' },
            ].map((step) => (
              <div key={step.n} className="grid sm:grid-cols-[80px_1fr] gap-2 sm:gap-8 items-baseline">
                <span className="text-sm font-medium text-[#333]">{step.n}</span>
                <div>
                  <h3 className="font-display text-2xl sm:text-3xl text-white">{step.title}</h3>
                  <p className="mt-3 text-sm text-[#888] leading-relaxed max-w-md">{step.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── PULL QUOTE ─────────────────────────────────────── */}
      <section className="section-rule flex items-center min-h-[60vh] px-6 sm:px-12 py-24">
        <blockquote className="max-w-3xl mx-auto text-center">
          <p className="font-display text-[clamp(1.6rem,5vw,3.5rem)] leading-[1.1] text-white">
            &ldquo;Your glow-up should look like{' '}
            <em className="text-accent">you</em>
            &nbsp;&mdash; not a filtered stranger.&rdquo;
          </p>
        </blockquote>
      </section>

      {/* ── WHAT YOU GET ───────────────────────────────────── */}
      <section className="section-rule px-6 sm:px-12 py-24 sm:py-40">
        <div className="max-w-5xl">
          <p className="text-xs tracking-[0.25em] uppercase text-[#555] mb-20">
            What you get
          </p>

          <div className="space-y-16 sm:space-y-24">
            <div className="grid sm:grid-cols-2 gap-4 sm:gap-20">
              <h3 className="font-display text-2xl sm:text-3xl text-white leading-snug">
                Ranked recommendations
              </h3>
              <p className="text-sm sm:text-base text-[#888] leading-relaxed sm:pt-2">
                Specific changes ordered by impact. Hair, grooming, eyebrows, clothing, facial hair, lighting — scored and prioritised.
              </p>
            </div>

            <div className="h-px bg-[#1a1a1a]" aria-hidden="true" />

            <div className="grid sm:grid-cols-2 gap-4 sm:gap-20">
              <h3 className="font-display text-2xl sm:text-3xl text-white leading-snug">
                Before &amp; after card
              </h3>
              <p className="text-sm sm:text-base text-[#888] leading-relaxed sm:pt-2">
                A shareable transformation card with your photo and top improvements. Post it, send it, or save it.
              </p>
            </div>

            <div className="h-px bg-[#1a1a1a]" aria-hidden="true" />

            <div className="grid sm:grid-cols-2 gap-4 sm:gap-20">
              <h3 className="font-display text-2xl sm:text-3xl text-white leading-snug">
                Style advisor
              </h3>
              <p className="text-sm sm:text-base text-[#888] leading-relaxed sm:pt-2">
                Chat with Ada, your AI style coach. Follow-up questions, deeper insights, weekly check-ins.
              </p>
            </div>

            <div className="h-px bg-[#1a1a1a]" aria-hidden="true" />

            <div className="grid sm:grid-cols-2 gap-4 sm:gap-20">
              <h3 className="font-display text-2xl sm:text-3xl text-white leading-snug">
                Identity preserved
              </h3>
              <p className="text-sm sm:text-base text-[#888] leading-relaxed sm:pt-2">
                Three layers of identity protection — model conditioning, ArcFace verification, and prompt design. Your glow-up looks like you.
              </p>
            </div>
          </div>
        </div>
      </section>

      {/* ── CLOSING CTA ────────────────────────────────────── */}
      <section className="section-rule flex flex-col justify-center min-h-[80vh] px-6 sm:px-12 py-24">
        <div className="max-w-3xl">
          <h2 className="font-display text-[clamp(2.5rem,9vw,6.5rem)] leading-[0.9] tracking-[-0.02em] text-white">
            Ready for
            <br />
            <em className="text-accent">yours?</em>
          </h2>
          <p className="mt-8 text-sm sm:text-base text-[#888] max-w-sm leading-relaxed">
            Free to try. Just a selfie and thirty seconds.
          </p>
          <div className="mt-10 flex items-center gap-6">
            <Link
              href={APP_STORE_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-2 bg-white text-[#0a0a0a] text-sm font-medium px-7 py-3.5 rounded-full transition-opacity hover:opacity-85 active:opacity-70"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.8-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z" />
              </svg>
              Download for iOS
            </Link>
            <Link
              href={PLAY_STORE_URL}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-[#888] hover:text-white transition-colors underline underline-offset-4 decoration-[#333] hover:decoration-[#888]"
            >
              Android
            </Link>
          </div>
        </div>
      </section>

      {/* ── FOOTER ───────────────────────────────────────── */}
      <footer className="section-rule px-6 sm:px-12 py-8 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 text-xs text-[#444]">
        <span>&copy; {new Date().getFullYear()} {SITE_NAME}</span>
        <div className="flex gap-6">
          <Link href="#" className="hover:text-[#888] transition-colors">Privacy</Link>
          <Link href="#" className="hover:text-[#888] transition-colors">Terms</Link>
        </div>
      </footer>
    </main>
  );
}
