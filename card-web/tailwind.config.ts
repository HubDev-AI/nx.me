import type { Config } from 'tailwindcss';

const config: Config = {
  content: [
    './src/pages/**/*.{js,ts,jsx,tsx,mdx}',
    './src/components/**/*.{js,ts,jsx,tsx,mdx}',
    './src/app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        // NXME design tokens — dark-first, before/after dual-accent architecture
        after: {
          50: '#FFF1F3',
          100: '#FFE4E8',
          200: '#FECDD5',
          300: '#FDA4B4',
          400: '#FB7091',
          500: '#F43F5E',
          600: '#E11D48',
          700: '#BE123C',
          800: '#9F1239',
          900: '#881337',
        },
        before: {
          50: '#F8FAFC',
          100: '#F1F5F9',
          200: '#E2E8F0',
          300: '#CBD5E1',
          400: '#94A3B8',
          500: '#64748B',
          600: '#475569',
          700: '#334155',
          800: '#1E293B',
          900: '#0F172A',
        },
        surface: {
          page: '#080808',
          card: '#111111',
          elevated: '#1A1A1A',
          subtle: '#222222',
        },
        border: {
          default: '#2A2A2A',
          strong: '#3A3A3A',
        },
        content: {
          primary: '#F8F8F8',
          secondary: '#A0A0A0',
          disabled: '#555555',
          inverse: '#111111',
        },
        glow: {
          DEFAULT: '#FF8C42',
          soft: 'rgba(255, 140, 66, 0.25)',
          ring: 'rgba(255, 140, 66, 0.40)',
        },
      },
      fontFamily: {
        sans: ['var(--font-inter)', 'system-ui', 'sans-serif'],
      },
      backgroundImage: {
        'before-overlay': 'rgba(15, 23, 42, 0.72)',
        'after-overlay': 'rgba(244, 63, 94, 0.08)',
      },
    },
  },
  plugins: [],
};

export default config;
