import Link from 'next/link';

import { buildTheme } from '@/components/theme-provider';
import {
  APP_STORE_URL,
  PLAY_STORE_URL,
  PRIVACY_URL,
  SITE_NAME,
  TERMS_URL,
} from '@/config/constants';

/**
 * Photography-driven editorial landing page.
 * Each refresh: different hero, before/after pair, and accent color.
 * Features aligned to generation-spec.md keyword categories.
 */
/** Server-side dynamic — fresh random theme on every request */
export const dynamic = 'force-dynamic';

export default function HomePage() {
  const t = buildTheme();

  return (
    <main className="bg-surface-page text-content-primary" style={{ '--accent': t.accent } as React.CSSProperties}>

      {/* ── HERO — parallax image, 120vh so face isn't cropped ── */}
      <section className="relative min-h-screen overflow-hidden">
        {/* Image container: 120% height for parallax room, sticks to top */}
        <div className="absolute inset-x-0 top-0 h-[120vh] hero-parallax">
          {/* eslint-disable-next-line @next/next/no-img-element */}
          <img src={t.hero} alt="" className="w-full h-full object-cover object-center" role="presentation" />
        </div>
        {/* Gradient: stronger at bottom for text, subtle vignette at top */}
        <div className="absolute inset-0 bg-gradient-to-t from-surface-page via-surface-page/50 to-surface-page/20" />

        <div className="relative z-10 min-h-screen flex flex-col justify-end px-6 sm:px-12 pb-16 sm:pb-24">
          <p className="text-xs tracking-[0.25em] uppercase text-white/40 mb-6">{SITE_NAME}</p>
          <h1 className="font-display text-[clamp(3rem,11vw,7.5rem)] leading-[0.9] tracking-[-0.02em] text-white max-w-3xl">
            Your style,<br />
            <em style={{ color: 'var(--accent)' }}>elevated.</em>
          </h1>
          <p className="mt-6 text-sm sm:text-base text-white/50 max-w-sm leading-relaxed">
            AI-powered style recommendations. See your transformation before you commit.
          </p>
          <div className="mt-8 flex items-center gap-6">
            <Link href={APP_STORE_URL} prefetch={false} target="_blank" rel="noopener noreferrer"
              className="inline-flex items-center gap-2 text-content-inverse text-sm font-medium px-7 py-3.5 rounded-full transition-opacity hover:opacity-85 active:opacity-70"
              style={{ backgroundColor: 'var(--accent)' }}>
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.8-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z" />
              </svg>
              Get the app
            </Link>
            <Link href={PLAY_STORE_URL} prefetch={false} target="_blank" rel="noopener noreferrer"
              className="text-sm text-white/40 hover:text-white/70 transition-colors underline underline-offset-4 decoration-white/20">
              Android
            </Link>
          </div>
        </div>
      </section>

      {/* ── THE TRANSFORMATION ────────────────────────────────
          Two contrasting portraits side by side. No labels —
          the visual contrast speaks for itself.
      ─────────────────────────────────────────────────────── */}
      <section className="section-rule">
        <div className="px-6 sm:px-12 py-16 sm:py-24">
          <h2 className="text-xs tracking-[0.25em] uppercase text-content-tertiary mb-12 font-normal">The transformation</h2>
        </div>
        <div className="grid grid-cols-2">
          <div className="relative aspect-[3/4] sm:aspect-[4/5]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={t.before} alt="Everyday look" className="absolute inset-0 w-full h-full object-cover" />
            <div className="absolute inset-0 bg-gradient-to-t from-surface-page/70 to-transparent" />
          </div>
          <div className="relative aspect-[3/4] sm:aspect-[4/5]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={t.after} alt="Elevated style" className="absolute inset-0 w-full h-full object-cover" />
            <div className="absolute inset-0 bg-gradient-to-t from-surface-page/70 to-transparent" />
          </div>
        </div>
        <div className="px-6 sm:px-12 py-16 sm:py-24">
          <p className="font-display text-2xl sm:text-4xl text-white leading-snug max-w-2xl">
            Same person. Different presence.<br />
            <em className="text-white/40">That&apos;s what a glow-up looks like.</em>
          </p>
        </div>
      </section>

      {/* ── MANIFESTO ──────────────────────────────────────── */}
      <section className="section-rule px-6 sm:px-12 py-24 sm:py-40">
        <div className="max-w-4xl">
          <p className="font-display text-[clamp(1.5rem,4.5vw,3.2rem)] leading-[1.15] text-white">
            We don&apos;t smooth your skin.<br />
            We don&apos;t change your face.<br />
            <em style={{ color: 'var(--accent)' }}>We show you what your style could be.</em>
          </p>
        </div>
      </section>

      {/* ── WHAT WE ANALYSE ────────────────────────────────── */}
      <section className="section-rule">
        <div className="px-6 sm:px-12 py-16 sm:py-24">
          <h2 className="text-xs tracking-[0.25em] uppercase text-content-tertiary font-normal">What we analyse</h2>
        </div>

        <div className="grid sm:grid-cols-2">
          <div className="relative aspect-[4/3]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={t.hair} alt="Hair styling" className="absolute inset-0 w-full h-full object-cover" />
          </div>
          <div className="flex items-center px-6 sm:px-12 py-12 sm:py-0">
            <div>
              <h3 className="font-display text-3xl sm:text-4xl text-white">Hair</h3>
              <p className="mt-4 text-sm text-content-secondary leading-relaxed max-w-sm">
                Cut, texture, colour, styling. From textured crops to soft waves — 30 styling options matched to your face shape.
              </p>
            </div>
          </div>
        </div>

        <div className="grid sm:grid-cols-2">
          <div className="flex items-center px-6 sm:px-12 py-12 sm:py-0 order-2 sm:order-1">
            <div>
              <h3 className="font-display text-3xl sm:text-4xl text-white">Clothing</h3>
              <p className="mt-4 text-sm text-content-secondary leading-relaxed max-w-sm">
                Fitted blazers, leather jackets, smart casual, streetwear. The right silhouette changes everything.
              </p>
            </div>
          </div>
          <div className="relative aspect-[4/3] order-1 sm:order-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={t.clothing} alt="Clothing and style" className="absolute inset-0 w-full h-full object-cover" />
          </div>
        </div>

        <div className="grid sm:grid-cols-2">
          <div className="relative aspect-[4/3]">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={t.grooming} alt="Grooming and skincare" className="absolute inset-0 w-full h-full object-cover" />
          </div>
          <div className="flex items-center px-6 sm:px-12 py-12 sm:py-0">
            <div>
              <h3 className="font-display text-3xl sm:text-4xl text-white">Grooming</h3>
              <p className="mt-4 text-sm text-content-secondary leading-relaxed max-w-sm">
                Brows, facial hair, skin health. Plus lighting that brings it all together.
              </p>
            </div>
          </div>
        </div>

        {/* Accessories — reversed layout */}
        <div className="grid sm:grid-cols-2">
          <div className="flex items-center px-6 sm:px-12 py-12 sm:py-0 order-2 sm:order-1">
            <div>
              <h3 className="font-display text-3xl sm:text-4xl text-white">Accessories</h3>
              <p className="mt-4 text-sm text-content-secondary leading-relaxed max-w-sm">
                Glasses, watches, jewellery, scarves. The details that complete the look.
              </p>
            </div>
          </div>
          <div className="relative aspect-[4/3] order-1 sm:order-2">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={t.accessories} alt="Accessories and details" className="absolute inset-0 w-full h-full object-cover" />
          </div>
        </div>

        <div className="px-6 sm:px-12 py-16 sm:py-24">
          <p className="text-xs tracking-[0.25em] uppercase text-content-tertiary mb-8">All categories</p>
          <div className="flex flex-wrap gap-3">
            {['Hair', 'Eyebrows', 'Facial hair', 'Clothing', 'Accessories', 'Grooming', 'Lighting'].map((cat) => (
              <span key={cat} className="px-4 py-2 text-xs tracking-wide border rounded-full"
                style={{ color: 'var(--accent)', borderColor: 'color-mix(in srgb, var(--accent) 25%, transparent)' }}>
                {cat}
              </span>
            ))}
          </div>
        </div>
      </section>

      {/* ── HOW IT WORKS ───────────────────────────────────── */}
      <section className="section-rule px-6 sm:px-12 py-24 sm:py-40">
        <div className="max-w-5xl">
          <h2 className="text-xs tracking-[0.25em] uppercase text-content-tertiary mb-20 font-normal">How it works</h2>
          <div className="space-y-16 sm:space-y-20">
            {[
              { n: '01', title: 'Upload a selfie', desc: 'One photo. No angles, no filters. Just you.' },
              { n: '02', title: 'Get your analysis', desc: 'AI evaluates hair, grooming, clothing, and more — ranked by impact.' },
              { n: '03', title: 'See the glow-up', desc: 'A before & after card with personalised recommendations you can share.' },
            ].map((step) => (
              <div key={step.n} className="grid sm:grid-cols-[80px_1fr] gap-2 sm:gap-8 items-baseline">
                <span className="text-sm font-medium" style={{ color: 'color-mix(in srgb, var(--accent) 40%, transparent)' }}>{step.n}</span>
                <div>
                  <h3 className="font-display text-2xl sm:text-3xl text-white">{step.title}</h3>
                  <p className="mt-3 text-sm text-content-secondary leading-relaxed max-w-md">{step.desc}</p>
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
            <em style={{ color: 'var(--accent)' }}>you</em>
            &nbsp;&mdash; not a filtered stranger.&rdquo;
          </p>
        </blockquote>
      </section>

      {/* ── WHAT YOU GET ───────────────────────────────────── */}
      <section className="section-rule px-6 sm:px-12 py-24 sm:py-40">
        <div className="max-w-5xl">
          <h2 className="text-xs tracking-[0.25em] uppercase text-content-tertiary mb-20 font-normal">What you get</h2>
          <div className="space-y-16 sm:space-y-24">
            {[
              { title: 'Ranked recommendations', desc: 'Specific changes ordered by impact. Hair, grooming, eyebrows, clothing, accessories, lighting — scored and prioritised.' },
              { title: 'Before & after card', desc: 'A shareable transformation card with your photo and top improvements. Post it, send it, or save it.' },
              { title: 'Style advisor', desc: 'Chat with Ada, your AI style coach. Follow-up questions, deeper insights, weekly check-ins.' },
              { title: 'Identity preserved', desc: 'Three layers of identity protection — model conditioning, ArcFace verification, and prompt design. Your glow-up looks like you.' },
            ].map((item, i) => (
              <div key={item.title}>
                {i > 0 && <div className="h-px bg-surface-divider mb-16 sm:mb-24" aria-hidden="true" />}
                <div className="grid sm:grid-cols-2 gap-4 sm:gap-20">
                  <h3 className="font-display text-2xl sm:text-3xl text-white leading-snug">{item.title}</h3>
                  <p className="text-sm sm:text-base text-content-secondary leading-relaxed sm:pt-2">{item.desc}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* ── CLOSING CTA ────────────────────────────────────── */}
      <section className="section-rule flex flex-col justify-center min-h-[80vh] px-6 sm:px-12 py-24">
        <div className="max-w-3xl">
          <h2 className="font-display text-[clamp(2.5rem,9vw,6.5rem)] leading-[0.9] tracking-[-0.02em] text-white">
            Ready for<br />
            <em style={{ color: 'var(--accent)' }}>yours?</em>
          </h2>
          <p className="mt-8 text-sm sm:text-base text-content-secondary max-w-sm leading-relaxed">
            Free to try. Just a selfie and thirty seconds.
          </p>
          <div className="mt-10 flex items-center gap-6">
            <Link href={APP_STORE_URL} prefetch={false} target="_blank" rel="noopener noreferrer"
              className="inline-flex items-center gap-2 text-content-inverse text-sm font-medium px-7 py-3.5 rounded-full transition-opacity hover:opacity-85 active:opacity-70"
              style={{ backgroundColor: 'var(--accent)' }}>
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
                <path d="M18.71 19.5c-.83 1.24-1.71 2.45-3.05 2.47-1.34.03-1.77-.79-3.29-.79-1.53 0-2 .77-3.27.82-1.31.05-2.3-1.32-3.14-2.53C4.25 17 2.94 12.45 4.7 9.39c.87-1.52 2.43-2.48 4.12-2.51 1.28-.02 2.5.87 3.29.87.78 0 2.26-1.07 3.8-.91.65.03 2.47.26 3.64 1.98-.09.06-2.17 1.28-2.15 3.81.03 3.02 2.65 4.03 2.68 4.04-.03.07-.42 1.44-1.38 2.83M13 3.5c.73-.83 1.94-1.46 2.94-1.5.13 1.17-.34 2.35-1.04 3.19-.69.85-1.83 1.51-2.95 1.42-.15-1.15.41-2.35 1.05-3.11z" />
              </svg>
              Download for iOS
            </Link>
            <Link href={PLAY_STORE_URL} prefetch={false} target="_blank" rel="noopener noreferrer"
              className="text-sm text-content-secondary hover:text-white transition-colors underline underline-offset-4 decoration-content-faint hover:decoration-content-secondary">
              Android
            </Link>
          </div>
        </div>
      </section>

      {/* ── FOOTER ───────────────────────────────────────── */}
      <footer className="section-rule px-6 sm:px-12 py-8 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4 text-xs text-content-disabled">
        <span>&copy; {new Date().getFullYear()} {SITE_NAME}</span>
        <div className="flex gap-6">
          <Link href={PRIVACY_URL} prefetch={false} className="hover:text-content-secondary transition-colors">Privacy</Link>
          <Link href={TERMS_URL} prefetch={false} className="hover:text-content-secondary transition-colors">Terms</Link>
        </div>
      </footer>
    </main>
  );
}
