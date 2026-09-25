import '@testing-library/jest-dom';

// Mock react-markdown to avoid ESM parsing issues in Jest
jest.mock('react-markdown', () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => children,
}));

// Mock sessionStorage
const sessionStorageMock: Record<string, string> = {};

global.sessionStorage = {
  getItem: (key: string) => sessionStorageMock[key] || null,
  setItem: (key: string, value: string) => {
    sessionStorageMock[key] = value.toString();
  },
  removeItem: (key: string) => {
    delete sessionStorageMock[key];
  },
  clear: () => {
    Object.keys(sessionStorageMock).forEach((key) => {
      delete sessionStorageMock[key];
    });
  },
  length: Object.keys(sessionStorageMock).length,
  key: (index: number) => {
    const keys = Object.keys(sessionStorageMock);
    return keys[index] || null;
  },
} as Storage;

// Mock window.location with full properties
delete (window as unknown as Record<string, unknown>).location;
Object.defineProperty(window, 'location', {
  value: {
    href: '',
    origin: 'http://localhost',
    protocol: 'http:',
    host: 'localhost',
    hostname: 'localhost',
    port: '',
    pathname: '/',
    search: '',
    hash: '',
    reload: jest.fn(),
  },
  writable: true,
});
