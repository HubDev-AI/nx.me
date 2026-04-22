/** Mirror of backend GenerationAction registry — slug → display metadata. */
export interface ActionDescriptor {
  readonly slug: string;
  readonly displayName: string;
  readonly sourceType: string;
  readonly postKind: 'glowup' | 'makeup';
}

export const GENERATION_ACTIONS: readonly ActionDescriptor[] = [
  {
    slug: 'glowup',
    displayName: 'Glow-Up',
    sourceType: 'glowup_analysis',
    postKind: 'glowup',
  },
  {
    slug: 'makeup',
    displayName: 'Makeup',
    sourceType: 'makeup_session',
    postKind: 'makeup',
  },
] as const;

export function getActionBySourceType(sourceType: string): ActionDescriptor | undefined {
  return GENERATION_ACTIONS.find((a) => a.sourceType === sourceType);
}
