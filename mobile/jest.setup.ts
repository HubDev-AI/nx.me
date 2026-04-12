import '@testing-library/jest-native/extend-expect';

// Mock react-native-mmkv (native module, unavailable in Jest env)
jest.mock('react-native-mmkv', () => ({
  MMKV: jest.fn().mockImplementation(() => {
    const store = new Map<string, string>();
    return {
      set: (k: string, v: string) => store.set(k, v),
      getString: (k: string) => store.get(k),
      delete: (k: string) => store.delete(k),
      clearAll: () => store.clear(),
      getAllKeys: () => Array.from(store.keys()),
    };
  }),
}));

// Silence Sentry in tests
jest.mock('@sentry/react-native', () => ({
  init: jest.fn(),
  captureException: jest.fn(),
  captureMessage: jest.fn(),
  addBreadcrumb: jest.fn(),
  wrap: (component: unknown) => component,
}));
