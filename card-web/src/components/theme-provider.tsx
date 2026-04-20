/* Theme builder — works on both server and client */

import { THEME_ACCENTS } from '@/config/constants';
import { POOLS } from '@/data/demo-themes';

function pick<T>(arr: ReadonlyArray<T>): T {
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
    accent: pick(THEME_ACCENTS),
  };
}
