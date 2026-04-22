/** Card-web-side action descriptors — mirrors backend GenerationAction slugs for display. */
export interface ActionDescriptor {
  slug: string;
  segment: string;
  label: string;
}

export const GENERATION_ACTIONS: readonly ActionDescriptor[] = [
  { slug: 'glowup_analysis', segment: 'glow-up', label: 'Glow-Up Analysis' },
  { slug: 'makeup_session', segment: 'makeup', label: 'Makeup Look' },
];

export function getActionBySlug(slug: string): ActionDescriptor | undefined {
  return GENERATION_ACTIONS.find((a) => a.slug === slug);
}
