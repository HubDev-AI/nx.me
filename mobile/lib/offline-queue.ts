import { createMMKV, type MMKV } from 'react-native-mmkv';

export interface QueuedMutation {
  id: string;
  mutationKey: readonly unknown[];
  variables: unknown;
  createdAt: number;
  /** Incremented on each failed replay attempt. Capped by the replay worker. */
  replayAttempts: number;
}

const QUEUE_KEY = 'queue';

export class OfflineMutationQueue {
  private storage: MMKV;

  constructor(id: string = 'nxme-mutation-queue') {
    this.storage = createMMKV({ id });
  }

  list(): QueuedMutation[] {
    const raw = this.storage.getString(QUEUE_KEY);
    if (!raw) return [];
    try {
      return JSON.parse(raw) as QueuedMutation[];
    } catch {
      return [];
    }
  }

  enqueue(mutation: QueuedMutation): void {
    const current = this.list();
    current.push(mutation);
    this.storage.set(QUEUE_KEY, JSON.stringify(current));
  }

  dequeue(id: string): void {
    const current = this.list().filter((m) => m.id !== id);
    this.storage.set(QUEUE_KEY, JSON.stringify(current));
  }

  clear(): void {
    this.storage.remove(QUEUE_KEY);
  }
}

/** Shared singleton for the app. */
export const mutationQueue = new OfflineMutationQueue();
