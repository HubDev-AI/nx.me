import '@testing-library/jest-native/extend-expect';

// Mock react-native-mmkv (native module, unavailable in Jest env).
// v4 exports `MMKV` as a type and `createMMKV` as the runtime factory.
// Stores are keyed by id so multiple instances with the same id share state
// (matches real MMKV persistence semantics).
jest.mock('react-native-mmkv', () => {
  const stores = new Map<string, Map<string, unknown>>();
  const factory = ({ id = 'default' }: { id?: string } = {}) => {
    if (!stores.has(id)) stores.set(id, new Map());
    const store = stores.get(id)!;
    return {
      set: (k: string, v: unknown) => store.set(k, v),
      getString: (k: string) => {
        const v = store.get(k);
        return typeof v === 'string' ? v : undefined;
      },
      getNumber: (k: string) => {
        const v = store.get(k);
        return typeof v === 'number' ? v : undefined;
      },
      getBoolean: (k: string) => {
        const v = store.get(k);
        return typeof v === 'boolean' ? v : undefined;
      },
      remove: (k: string) => store.delete(k),
      clearAll: () => store.clear(),
      getAllKeys: () => Array.from(store.keys()),
      contains: (k: string) => store.has(k),
    };
  };
  return {
    MMKV: jest.fn().mockImplementation(factory), // type-only in real lib; keep callable for legacy code
    createMMKV: jest.fn().mockImplementation(factory),
  };
});

// Silence Sentry in tests
jest.mock('@sentry/react-native', () => ({
  init: jest.fn(),
  captureException: jest.fn(),
  captureMessage: jest.fn(),
  addBreadcrumb: jest.fn(),
  wrap: (component: unknown) => component,
}));
