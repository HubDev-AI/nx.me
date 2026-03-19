'use client';

import { useEffect, useState } from 'react';

/**
 * Demographic pools — each render picks ONE demographic,
 * then assembles a fully consistent theme from that pool.
 * No gender mixing ever.
 */

const ACCENTS = [
  '#F43F5E', '#14B8A6', '#D4A060', '#38BDF8', '#FB923C',
  '#6366F1', '#EF4444', '#A78BFA', '#F472B6', '#E879F9',
  '#34D399', '#F59E0B', '#EC4899', '#8B5CF6', '#10B981',
];

interface DemoPool {
  heroes: string[];
  pairs: { before: string; after: string }[];
  hair: string[];
  clothing: string[];
  grooming: string[];
  accessories: string[];
}

const MEN: DemoPool = {
  heroes: ['/images/hero-1.jpg', '/images/hero-3.jpg', '/images/hero-7.jpg', '/images/hero-10.jpg', '/images/hero-11.jpg'],
  pairs: [
    { before: '/images/before-1.jpg', after: '/images/after-1.jpg' },
    { before: '/images/before-2.jpg', after: '/images/after-2.jpg' },
    { before: '/images/before-3.jpg', after: '/images/after-3.jpg' },
    { before: '/images/before-4.jpg', after: '/images/after-4.jpg' },
    { before: '/images/before-11.jpg', after: '/images/after-11.jpg' },
    { before: '/images/before-12.jpg', after: '/images/after-12.jpg' },
    { before: '/images/before-13.jpg', after: '/images/after-13.jpg' },
    { before: '/images/before-21.jpg', after: '/images/after-21.jpg' },
    { before: '/images/before-22.jpg', after: '/images/after-22.jpg' },
    { before: '/images/before-23.jpg', after: '/images/after-23.jpg' },
    { before: '/images/before-24.jpg', after: '/images/after-24.jpg' },
    { before: '/images/before-25.jpg', after: '/images/after-25.jpg' },
    { before: '/images/before-26.jpg', after: '/images/after-26.jpg' },
    { before: '/images/before-27.jpg', after: '/images/after-27.jpg' },
  ],
  hair: ['/images/detail-hair-men.jpg', '/images/detail-hair-men-2.jpg', '/images/detail-hair.jpg'],
  clothing: ['/images/detail-clothing-men.jpg', '/images/detail-clothing-men-2.jpg', '/images/detail-accessories.jpg'],
  grooming: ['/images/detail-grooming-men.jpg', '/images/detail-grooming-men-2.jpg', '/images/detail-grooming.jpg'],
  accessories: ['/images/detail-accessories-men.jpg', '/images/detail-accessories.jpg'],
};

const WOMEN: DemoPool = {
  heroes: ['/images/hero-2.jpg', '/images/hero-4.jpg', '/images/hero-8.jpg', '/images/hero-9.jpg', '/images/hero-12.jpg'],
  pairs: [
    { before: '/images/before-5.jpg', after: '/images/after-5.jpg' },
    { before: '/images/before-6.jpg', after: '/images/after-6.jpg' },
    { before: '/images/before-7.jpg', after: '/images/after-7.jpg' },
    { before: '/images/before-8.jpg', after: '/images/after-8.jpg' },
    { before: '/images/before-14.jpg', after: '/images/after-14.jpg' },
    { before: '/images/before-15.jpg', after: '/images/after-15.jpg' },
    { before: '/images/before-16.jpg', after: '/images/after-16.jpg' },
    { before: '/images/before-28.jpg', after: '/images/after-28.jpg' },
    { before: '/images/before-29.jpg', after: '/images/after-29.jpg' },
    { before: '/images/before-30.jpg', after: '/images/after-30.jpg' },
    { before: '/images/before-31.jpg', after: '/images/after-31.jpg' },
    { before: '/images/before-32.jpg', after: '/images/after-32.jpg' },
    { before: '/images/before-33.jpg', after: '/images/after-33.jpg' },
    { before: '/images/before-34.jpg', after: '/images/after-34.jpg' },
  ],
  hair: ['/images/detail-hair-women.jpg', '/images/detail-hair-women-2.jpg'],
  clothing: ['/images/detail-clothing-women.jpg', '/images/detail-clothing-women-2.jpg'],
  grooming: ['/images/detail-grooming-women.jpg', '/images/detail-grooming-women-2.jpg'],
  accessories: ['/images/detail-accessories-women.jpg'],
};

const YOUNG: DemoPool = {
  heroes: ['/images/hero-3.jpg', '/images/hero-7.jpg', '/images/hero-8.jpg', '/images/hero-11.jpg'],
  pairs: [
    { before: '/images/before-9.jpg', after: '/images/after-9.jpg' },
    { before: '/images/before-10.jpg', after: '/images/after-10.jpg' },
    { before: '/images/before-17.jpg', after: '/images/after-17.jpg' },
    { before: '/images/before-18.jpg', after: '/images/after-18.jpg' },
    { before: '/images/before-19.jpg', after: '/images/after-19.jpg' },
    { before: '/images/before-20.jpg', after: '/images/after-20.jpg' },
    { before: '/images/before-35.jpg', after: '/images/after-35.jpg' },
    { before: '/images/before-36.jpg', after: '/images/after-36.jpg' },
    { before: '/images/before-37.jpg', after: '/images/after-37.jpg' },
    { before: '/images/before-38.jpg', after: '/images/after-38.jpg' },
    { before: '/images/before-39.jpg', after: '/images/after-39.jpg' },
    { before: '/images/before-40.jpg', after: '/images/after-40.jpg' },
  ],
  hair: ['/images/detail-hair-teen.jpg', '/images/detail-hair-teen-2.jpg'],
  clothing: ['/images/detail-clothing-teen.jpg', '/images/detail-clothing-teen-2.jpg'],
  grooming: ['/images/detail-grooming-teen.jpg', '/images/detail-grooming-teen-2.jpg'],
  accessories: ['/images/detail-accessories-teen.jpg'],
};

const POOLS = [MEN, WOMEN, YOUNG];

function pick<T>(arr: T[]): T {
  return arr[Math.floor(Math.random() * arr.length)] ?? arr[0] as T;
}

export interface Theme {
  before: string;
  after: string;
  hero: string;
  hair: string;
  clothing: string;
  grooming: string;
  accessories: string;
  accent: string;
}

function buildTheme(): Theme {
  const pool = pick(POOLS);
  const pair = pick(pool.pairs);
  return {
    before: pair.before,
    after: pair.after,
    hero: pick(pool.heroes),
    hair: pick(pool.hair),
    clothing: pick(pool.clothing),
    grooming: pick(pool.grooming),
    accessories: pick(pool.accessories),
    accent: pick(ACCENTS),
  };
}

const DEFAULT_THEME: Theme = {
  before: '/images/before-1.jpg',
  after: '/images/after-1.jpg',
  hero: '/images/hero-1.jpg',
  hair: '/images/detail-hair-men.jpg',
  clothing: '/images/detail-clothing-men.jpg',
  grooming: '/images/detail-grooming-men.jpg',
  accessories: '/images/detail-accessories-men.jpg',
  accent: '#F43F5E',
};

export function useTheme(): Theme {
  const [theme, setTheme] = useState<Theme>(DEFAULT_THEME);

  useEffect(() => {
    const t = buildTheme();
    setTheme(t);
    document.documentElement.style.setProperty('--accent', t.accent);
  }, []);

  return theme;
}
