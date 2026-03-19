'use client';

import { useEffect, useState } from 'react';

/**
 * Themed variants — each refresh picks one randomly.
 * Detail images (hair/clothing/grooming) match the demographic.
 * Accent color shifts the entire page personality.
 */
const THEMES = [
  // Men themes
  { hero: '/images/hero-1.jpg', before: '/images/before-1.jpg', after: '/images/after-1.jpg', hair: '/images/detail-hair-men.jpg', clothing: '/images/detail-clothing-men.jpg', grooming: '/images/detail-grooming-men.jpg', accent: '#F43F5E' },
  { hero: '/images/hero-3.jpg', before: '/images/before-3.jpg', after: '/images/after-3.jpg', hair: '/images/detail-hair-men.jpg', clothing: '/images/detail-clothing-men.jpg', grooming: '/images/detail-grooming-men.jpg', accent: '#14B8A6' },
  { hero: '/images/hero-1.jpg', before: '/images/before-4.jpg', after: '/images/after-4.jpg', hair: '/images/detail-hair.jpg', clothing: '/images/detail-accessories.jpg', grooming: '/images/detail-grooming.jpg', accent: '#38BDF8' },
  { hero: '/images/hero-3.jpg', before: '/images/before-2.jpg', after: '/images/after-2.jpg', hair: '/images/detail-hair-men.jpg', clothing: '/images/detail-clothing-men.jpg', grooming: '/images/detail-grooming-men.jpg', accent: '#D4A060' },
  // Women themes
  { hero: '/images/hero-2.jpg', before: '/images/before-5.jpg', after: '/images/after-5.jpg', hair: '/images/detail-hair-women.jpg', clothing: '/images/detail-clothing-women.jpg', grooming: '/images/detail-grooming-women.jpg', accent: '#A78BFA' },
  { hero: '/images/hero-4.jpg', before: '/images/before-6.jpg', after: '/images/after-6.jpg', hair: '/images/detail-hair-women.jpg', clothing: '/images/detail-clothing-women.jpg', grooming: '/images/detail-grooming-women.jpg', accent: '#F472B6' },
  { hero: '/images/hero-2.jpg', before: '/images/before-7.jpg', after: '/images/after-7.jpg', hair: '/images/detail-hair-women.jpg', clothing: '/images/detail-clothing-women.jpg', grooming: '/images/detail-grooming-women.jpg', accent: '#E879F9' },
  // Teen/neutral themes
  { hero: '/images/hero-4.jpg', before: '/images/before-8.jpg', after: '/images/after-8.jpg', hair: '/images/detail-hair-teen.jpg', clothing: '/images/detail-clothing-teen.jpg', grooming: '/images/detail-grooming-teen.jpg', accent: '#FB923C' },
  { hero: '/images/hero-1.jpg', before: '/images/before-9.jpg', after: '/images/after-9.jpg', hair: '/images/detail-hair-teen.jpg', clothing: '/images/detail-clothing-teen.jpg', grooming: '/images/detail-grooming-teen.jpg', accent: '#F43F5E' },
  { hero: '/images/hero-2.jpg', before: '/images/before-10.jpg', after: '/images/after-10.jpg', hair: '/images/detail-hair-teen.jpg', clothing: '/images/detail-clothing-teen.jpg', grooming: '/images/detail-grooming-teen.jpg', accent: '#34D399' },
];

export interface Theme {
  hero: string;
  before: string;
  after: string;
  hair: string;
  clothing: string;
  grooming: string;
  accent: string;
}

// eslint-disable-next-line @typescript-eslint/no-non-null-assertion -- constant array, index 0 always exists
const DEFAULT_THEME: Theme = THEMES[0]!;

/**
 * Client-side theme hook. Picks a random theme on mount.
 * Sets --accent CSS variable on document root.
 */
export function useTheme(): Theme {
  const [theme, setTheme] = useState<Theme>(DEFAULT_THEME);

  useEffect(() => {
    const idx = Math.floor(Math.random() * THEMES.length);
    const picked = THEMES[idx] ?? DEFAULT_THEME;
    setTheme(picked);
    document.documentElement.style.setProperty('--accent', picked.accent);
  }, []);

  return theme;
}
