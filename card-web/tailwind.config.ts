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
          page: '#0a0a0a',
          card: '#111111',
          elevated: '#181818',
          subtle: '#1f1f1f',
          divider: '#1a1a1a',
        },
        border: {
          default: 'rgba(255, 255, 255, 0.06)',
          strong: 'rgba(255, 255, 255, 0.12)',
        },
        content: {
          primary: '#e8e8e8',
          secondary: '#888888',
          tertiary: '#555555',
          muted: '#cccccc',
          faint: '#333333',
          disabled: '#444444',
          inverse: '#0a0a0a',
        },
        glow: {
          DEFAULT: '#FF8C42',
          soft: 'rgba(255, 140, 66, 0.20)',
          ring: 'rgba(255, 140, 66, 0.35)',
        },
      },
      fontFamily: {
        sans: ['var(--font-inter)', 'system-ui', 'sans-serif'],
        display: ['var(--font-display)', 'Georgia', 'Times New Roman', 'serif'],
      },
    },
  },
  plugins: [],
};

export default config;
