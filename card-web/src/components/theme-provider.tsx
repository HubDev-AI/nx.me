'use client';

import { useEffect, useState } from 'react';

/**
 * Pool-based theme system. Gender-audited pairs only.
 * Removed: pairs 16,32,38 (gender mismatch), pairs 18,21,23-27,33,36 (duplicates).
 * Every pair verified: same gender in both images.
 */

const ACCENTS = [
  '#F43F5E', '#14B8A6', '#D4A060', '#38BDF8', '#FB923C',
  '#6366F1', '#EF4444', '#A78BFA', '#F472B6', '#E879F9',
  '#34D399', '#F59E0B', '#EC4899', '#8B5CF6', '#10B981',
  '#0EA5E9', '#F97316', '#84CC16', '#E11D48', '#7C3AED',
];

interface DemoPool {
  heroes: string[];
  pairs: { before: string; after: string }[];
  hair: string[];
  clothing: string[];
  grooming: string[];
  accessories: string[];
}

// Verified M+M pairs only, no duplicates
const MEN: DemoPool = {
  heroes: [
    '/images/hero-1.jpg', '/images/hero-3.jpg', '/images/hero-7.jpg',
    '/images/hero-10.jpg', '/images/hero-11.jpg',
    '/images/after-1.jpg', '/images/after-3.jpg', '/images/after-22.jpg',
    '/images/before-3.jpg', '/images/before-1.jpg', '/images/after-37.jpg',
    '/images/after-9.jpg', '/images/before-22.jpg', '/images/after-12.jpg',
  ],
  pairs: [
    { before: '/images/before-1.jpg', after: '/images/after-1.jpg' },   // M+M verified
    { before: '/images/before-2.jpg', after: '/images/after-2.jpg' },   // M+M verified
    { before: '/images/before-3.jpg', after: '/images/after-3.jpg' },   // M+M verified
    { before: '/images/before-4.jpg', after: '/images/after-4.jpg' },   // M+M verified
    { before: '/images/before-9.jpg', after: '/images/after-9.jpg' },   // M+M verified
    { before: '/images/before-11.jpg', after: '/images/after-11.jpg' }, // M+M verified
    { before: '/images/before-12.jpg', after: '/images/after-12.jpg' }, // M+M verified
    { before: '/images/before-13.jpg', after: '/images/after-13.jpg' }, // M+M verified
    { before: '/images/before-17.jpg', after: '/images/after-17.jpg' }, // M+M verified
    { before: '/images/before-19.jpg', after: '/images/after-19.jpg' }, // M+M verified
    { before: '/images/before-22.jpg', after: '/images/after-22.jpg' }, // M+M verified
    { before: '/images/before-35.jpg', after: '/images/after-35.jpg' }, // M+M verified
    { before: '/images/before-37.jpg', after: '/images/after-37.jpg' }, // M+M verified
    { before: '/images/before-39.jpg', after: '/images/after-39.jpg' }, // M+M verified
  ],
  hair: ['/images/detail-hair-men.jpg', '/images/detail-hair-men-2.jpg', '/images/detail-hair.jpg', '/images/detail-hair-men-3.jpg', '/images/detail-hair-men-4.jpg', '/images/detail-hair-men-5.jpg'],
  clothing: ['/images/detail-clothing-men.jpg', '/images/detail-clothing-men-2.jpg', '/images/detail-clothing-men-3.jpg', '/images/detail-clothing-men-4.jpg', '/images/detail-clothing-men-5.jpg'],
  grooming: ['/images/detail-grooming-men.jpg', '/images/detail-grooming-men-2.jpg', '/images/detail-grooming.jpg', '/images/detail-grooming-men-3.jpg', '/images/detail-grooming-men-4.jpg', '/images/detail-grooming-men-5.jpg'],
  accessories: ['/images/detail-accessories-men.jpg', '/images/detail-accessories-men-2.jpg', '/images/detail-accessories-men-3.jpg', '/images/detail-accessories-men-4.jpg', '/images/detail-accessories-men-5.jpg'],
};

// Verified F+F pairs only, no duplicates
const WOMEN: DemoPool = {
  heroes: [
    '/images/hero-2.jpg', '/images/hero-4.jpg', '/images/hero-8.jpg',
    '/images/hero-9.jpg', '/images/hero-12.jpg',
    '/images/after-5.jpg', '/images/after-6.jpg', '/images/after-7.jpg',
    '/images/after-28.jpg', '/images/after-29.jpg', '/images/before-7.jpg',
    '/images/after-14.jpg', '/images/after-31.jpg', '/images/before-34.jpg',
  ],
  pairs: [
    { before: '/images/before-5.jpg', after: '/images/after-5.jpg' },   // F+F verified
    { before: '/images/before-6.jpg', after: '/images/after-6.jpg' },   // F+F verified
    { before: '/images/before-7.jpg', after: '/images/after-7.jpg' },   // F+F verified
    { before: '/images/before-8.jpg', after: '/images/after-8.jpg' },   // F+F verified
    { before: '/images/before-10.jpg', after: '/images/after-10.jpg' }, // F+F verified
    { before: '/images/before-14.jpg', after: '/images/after-14.jpg' }, // F+F verified
    { before: '/images/before-15.jpg', after: '/images/after-15.jpg' }, // F+F verified
    { before: '/images/before-20.jpg', after: '/images/after-20.jpg' }, // F+F verified
    { before: '/images/before-28.jpg', after: '/images/after-28.jpg' }, // F+F verified
    { before: '/images/before-29.jpg', after: '/images/after-29.jpg' }, // F+F verified
    { before: '/images/before-30.jpg', after: '/images/after-30.jpg' }, // F+F verified
    { before: '/images/before-31.jpg', after: '/images/after-31.jpg' }, // F+F verified
    { before: '/images/before-34.jpg', after: '/images/after-34.jpg' }, // F+F verified
    { before: '/images/before-40.jpg', after: '/images/after-40.jpg' }, // F+F verified
  ],
  hair: ['/images/detail-hair-women.jpg', '/images/detail-hair-women-2.jpg', '/images/detail-hair-women-3.jpg', '/images/detail-hair-women-4.jpg', '/images/detail-hair-women-5.jpg'],
  clothing: ['/images/detail-clothing-women.jpg', '/images/detail-clothing-women-2.jpg', '/images/detail-clothing-women-3.jpg', '/images/detail-clothing-women-4.jpg', '/images/detail-clothing-women-5.jpg'],
  grooming: ['/images/detail-grooming-women.jpg', '/images/detail-grooming-women-2.jpg', '/images/detail-grooming-women-3.jpg', '/images/detail-grooming-women-4.jpg', '/images/detail-grooming-women-5.jpg'],
  accessories: ['/images/detail-accessories-women.jpg', '/images/detail-accessories-women-2.jpg', '/images/detail-accessories-women-3.jpg', '/images/detail-accessories-women-4.jpg', '/images/detail-accessories-women-5.jpg'],
};

// 20 young/teen pairs + dedicated teen detail images and heroes
const YOUNG: DemoPool = {
  heroes: [
    '/images/hero-13.jpg', '/images/hero-14.jpg', '/images/hero-15.jpg',
    '/images/hero-16.jpg', '/images/hero-3.jpg', '/images/hero-7.jpg',
    '/images/hero-8.jpg', '/images/hero-11.jpg', '/images/hero-12.jpg',
    '/images/after-41.jpg', '/images/after-42.jpg', '/images/before-46.jpg',
    '/images/before-47.jpg', '/images/after-48.jpg', '/images/before-51.jpg',
    '/images/after-43.jpg', '/images/before-42.jpg', '/images/after-51.jpg',
    '/images/before-49.jpg', '/images/after-46.jpg',
  ],
  pairs: [
    // Original young pairs
    { before: '/images/before-4.jpg', after: '/images/after-4.jpg' },
    { before: '/images/before-13.jpg', after: '/images/after-13.jpg' },
    { before: '/images/before-35.jpg', after: '/images/after-35.jpg' },
    { before: '/images/before-39.jpg', after: '/images/after-39.jpg' },
    { before: '/images/before-5.jpg', after: '/images/after-5.jpg' },
    { before: '/images/before-10.jpg', after: '/images/after-10.jpg' },
    { before: '/images/before-40.jpg', after: '/images/after-40.jpg' },
    { before: '/images/before-34.jpg', after: '/images/after-34.jpg' },
    // New teen pairs 41-52
    { before: '/images/before-41.jpg', after: '/images/after-41.jpg' },
    { before: '/images/before-42.jpg', after: '/images/after-42.jpg' },
    { before: '/images/before-43.jpg', after: '/images/after-43.jpg' },
    { before: '/images/before-44.jpg', after: '/images/after-44.jpg' },
    { before: '/images/before-45.jpg', after: '/images/after-45.jpg' },
    { before: '/images/before-46.jpg', after: '/images/after-46.jpg' },
    { before: '/images/before-47.jpg', after: '/images/after-47.jpg' },
    { before: '/images/before-48.jpg', after: '/images/after-48.jpg' },
    { before: '/images/before-49.jpg', after: '/images/after-49.jpg' },
    { before: '/images/before-50.jpg', after: '/images/after-50.jpg' },
    { before: '/images/before-51.jpg', after: '/images/after-51.jpg' },
    { before: '/images/before-52.jpg', after: '/images/after-52.jpg' },
  ],
  hair: ['/images/detail-hair-teen.jpg', '/images/detail-hair-teen-2.jpg', '/images/detail-hair-teen-3.jpg', '/images/detail-hair-teen-4.jpg', '/images/detail-hair-teen-5.jpg'],
  clothing: ['/images/detail-clothing-teen.jpg', '/images/detail-clothing-teen-2.jpg', '/images/detail-clothing-teen-3.jpg', '/images/detail-clothing-teen-4.jpg', '/images/detail-clothing-teen-5.jpg'],
  grooming: ['/images/detail-grooming-teen.jpg', '/images/detail-grooming-teen-2.jpg', '/images/detail-grooming-teen-3.jpg', '/images/detail-grooming-teen-4.jpg', '/images/detail-grooming-teen-5.jpg'],
  accessories: ['/images/detail-accessories-teen.jpg', '/images/detail-accessories-teen-2.jpg', '/images/detail-accessories-teen-3.jpg', '/images/detail-accessories-teen-4.jpg', '/images/detail-accessories-teen-5.jpg'],
};

// PRIMARY audience — young women. 20 dedicated pairs + own detail images + heroes.
const YOUNG_WOMEN: DemoPool = {
  heroes: [
    '/images/hero-17.jpg', '/images/hero-18.jpg', '/images/hero-19.jpg',
    '/images/hero-20.jpg', '/images/hero-21.jpg', '/images/hero-22.jpg',
    '/images/hero-2.jpg', '/images/hero-4.jpg', '/images/hero-8.jpg',
    '/images/hero-9.jpg', '/images/hero-12.jpg', '/images/hero-14.jpg',
    '/images/hero-16.jpg',
    '/images/after-53.jpg', '/images/after-54.jpg', '/images/before-55.jpg',
    '/images/after-58.jpg', '/images/before-65.jpg', '/images/after-67.jpg',
    '/images/before-72.jpg',
  ],
  pairs: [
    { before: '/images/before-53.jpg', after: '/images/after-53.jpg' },
    { before: '/images/before-54.jpg', after: '/images/after-54.jpg' },
    { before: '/images/before-55.jpg', after: '/images/after-55.jpg' },
    { before: '/images/before-56.jpg', after: '/images/after-56.jpg' },
    { before: '/images/before-57.jpg', after: '/images/after-57.jpg' },
    { before: '/images/before-58.jpg', after: '/images/after-58.jpg' },
    { before: '/images/before-59.jpg', after: '/images/after-59.jpg' },
    { before: '/images/before-60.jpg', after: '/images/after-60.jpg' },
    { before: '/images/before-61.jpg', after: '/images/after-61.jpg' },
    { before: '/images/before-62.jpg', after: '/images/after-62.jpg' },
    { before: '/images/before-63.jpg', after: '/images/after-63.jpg' },
    { before: '/images/before-64.jpg', after: '/images/after-64.jpg' },
    { before: '/images/before-65.jpg', after: '/images/after-65.jpg' },
    { before: '/images/before-66.jpg', after: '/images/after-66.jpg' },
    { before: '/images/before-67.jpg', after: '/images/after-67.jpg' },
    { before: '/images/before-68.jpg', after: '/images/after-68.jpg' },
    { before: '/images/before-69.jpg', after: '/images/after-69.jpg' },
    { before: '/images/before-70.jpg', after: '/images/after-70.jpg' },
    { before: '/images/before-71.jpg', after: '/images/after-71.jpg' },
    { before: '/images/before-72.jpg', after: '/images/after-72.jpg' },
  ],
  hair: ['/images/detail-hair-yw-1.jpg', '/images/detail-hair-yw-2.jpg', '/images/detail-hair-yw-3.jpg', '/images/detail-hair-yw-4.jpg', '/images/detail-hair-yw-5.jpg'],
  clothing: ['/images/detail-clothing-yw-1.jpg', '/images/detail-clothing-yw-2.jpg', '/images/detail-clothing-yw-3.jpg', '/images/detail-clothing-yw-4.jpg', '/images/detail-clothing-yw-5.jpg'],
  grooming: ['/images/detail-grooming-yw-1.jpg', '/images/detail-grooming-yw-2.jpg', '/images/detail-grooming-yw-3.jpg', '/images/detail-grooming-yw-4.jpg', '/images/detail-grooming-yw-5.jpg'],
  accessories: ['/images/detail-accessories-yw-1.jpg', '/images/detail-accessories-yw-2.jpg', '/images/detail-accessories-yw-3.jpg', '/images/detail-accessories-yw-4.jpg', '/images/detail-accessories-yw-5.jpg'],
};

// Weighted pool selection: YOUNG_WOMEN appears 4x (primary audience)
const POOLS = [YOUNG_WOMEN, YOUNG_WOMEN, YOUNG_WOMEN, YOUNG_WOMEN, MEN, WOMEN, YOUNG];

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
