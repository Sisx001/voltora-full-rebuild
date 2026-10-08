export {};

// Test-only browser API doubles; no production providers are mocked.

// Mock window.crypto for tests
if (!global.crypto) {
  Object.defineProperty(global, 'crypto', {
    value: {
      randomUUID: () => 'test-uuid-' + Date.now().toString(36),
    },
  });
}

// Mock navigator.clipboard for tests
if (!global.navigator.clipboard) {
  Object.defineProperty(global.navigator, 'clipboard', {
    value: {
      writeText: jest.fn(() => Promise.resolve()),
    },
  });
}
