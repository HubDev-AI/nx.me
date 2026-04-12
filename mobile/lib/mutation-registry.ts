/**
 * Registry of mutationFns keyed by serialized mutationKey.
 * Consumers of useAppMutation with queueOffline: true MUST register
 * their mutationFn here at module scope so the offline-replay worker
 * in _layout.tsx can execute queued mutations.
 */

type MutationFn = (variables: unknown) => Promise<unknown>;

const registry = new Map<string, MutationFn>();

function keyOf(mutationKey: readonly unknown[]): string {
  return JSON.stringify(mutationKey);
}

export function registerReplayableMutation(
  mutationKey: readonly unknown[],
  fn: MutationFn,
): void {
  registry.set(keyOf(mutationKey), fn);
}

export function lookupReplayableMutation(
  mutationKey: readonly unknown[],
): MutationFn | undefined {
  return registry.get(keyOf(mutationKey));
}
