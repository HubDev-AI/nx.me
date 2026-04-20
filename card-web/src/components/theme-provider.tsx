/* Theme builder — works on both server and client */

import { THEME_ACCENTS } from '@/config/constants';
import { POOLS } from '@/data/demo-themes';

function pickRandom<T>(arr: ReadonlyArray<T>): T {
  return arr[Math.floor(Math.random() * arr.length)] ?? (arr[0] as T);
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

export function buildTheme(): Theme {
  const pool = pickRandom(POOLS);
  const pair = pickRandom(pool.pairs);
  return {
    before: pair.before,
    after: pair.after,
    hero: pickRandom(pool.heroes),
    hair: pickRandom(pool.hair),
    clothing: pickRandom(pool.clothing),
    grooming: pickRandom(pool.grooming),
    accessories: pickRandom(pool.accessories),
    accent: pickRandom(THEME_ACCENTS),
  };
}
