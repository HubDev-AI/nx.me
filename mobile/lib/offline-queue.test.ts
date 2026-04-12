import { OfflineMutationQueue, type QueuedMutation } from './offline-queue';

// Override the global jest.setup.ts mock so stores are shared by id.
// This makes the "persists across instances" test meaningful and mirrors
// real MMKV semantics (same id → same underlying store).
// jest.mock is hoisted by babel-plugin-jest-hoist, so placement after imports is fine.
jest.mock('react-native-mmkv', () => {
  const stores = new Map<string, Map<string, string>>();
  const getStore = (id: string): Map<string, string> => {
    if (!stores.has(id)) stores.set(id, new Map<string, string>());
    return stores.get(id) as Map<string, string>;
  };
  const build = (id: string) => {
    const store = getStore(id);
    return {
      set: (k: string, v: string) => store.set(k, v),
      getString: (k: string) => store.get(k),
      remove: (k: string) => store.delete(k),
      clearAll: () => store.clear(),
      getAllKeys: () => Array.from(store.keys()),
    };
  };
  return {
    createMMKV: jest.fn().mockImplementation(({ id }: { id: string }) => build(id)),
    // Also expose MMKV as a callable for any caller that expects the old API.
    MMKV: jest.fn().mockImplementation(({ id }: { id: string }) => build(id)),
  };
});

describe('OfflineMutationQueue', () => {
  let queue: OfflineMutationQueue;

  beforeEach(() => {
    queue = new OfflineMutationQueue('test-queue');
    queue.clear();
  });

  it('starts empty', () => {
    expect(queue.list()).toEqual([]);
  });

  it('enqueues a mutation', () => {
    const mut: QueuedMutation = {
      id: 'm1',
      mutationKey: ['reportPost'],
      variables: { postId: 'p1' },
      createdAt: Date.now(),
    };
    queue.enqueue(mut);
    const items = queue.list();
    expect(items).toHaveLength(1);
    expect(items[0]?.id).toBe('m1');
  });

  it('dequeues by id', () => {
    queue.enqueue({ id: 'm1', mutationKey: ['a'], variables: {}, createdAt: 1 });
    queue.enqueue({ id: 'm2', mutationKey: ['b'], variables: {}, createdAt: 2 });
    queue.dequeue('m1');
    const items = queue.list();
    expect(items).toHaveLength(1);
    expect(items[0]?.id).toBe('m2');
  });

  it('preserves FIFO order', () => {
    queue.enqueue({ id: 'm1', mutationKey: ['a'], variables: {}, createdAt: 1 });
    queue.enqueue({ id: 'm2', mutationKey: ['b'], variables: {}, createdAt: 2 });
    queue.enqueue({ id: 'm3', mutationKey: ['c'], variables: {}, createdAt: 3 });
    expect(queue.list().map((m) => m.id)).toEqual(['m1', 'm2', 'm3']);
  });

  it('persists across instances (same storage id)', () => {
    queue.enqueue({ id: 'm1', mutationKey: ['a'], variables: {}, createdAt: 1 });
    const queue2 = new OfflineMutationQueue('test-queue');
    expect(queue2.list()).toHaveLength(1);
  });
});
