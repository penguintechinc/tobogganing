/// <reference types="vitest/globals" />
import '@testing-library/jest-dom'
import { vi } from 'vitest'

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: vi.fn().mockImplementation((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })),
})

// Mock window.location for redirect tests — keep origin intact for BrowserRouter
const originalLocation = window.location
Object.defineProperty(window, 'location', {
  writable: true,
  value: {
    ...originalLocation,
    href: 'http://localhost/',
    origin: 'http://localhost',
    assign: vi.fn(),
    replace: vi.fn(),
    reload: vi.fn(),
  },
})

// Suppress console.error for expected React test errors
const originalConsoleError = console.error
beforeEach(() => {
  console.error = (...args: unknown[]) => {
    const msg = String(args[0])
    // Suppress known expected warnings
    if (
      msg.includes('Warning:') ||
      msg.includes('ReactDOM.render') ||
      msg.includes('act(')
    ) {
      return
    }
    originalConsoleError(...args)
  }
})

afterEach(() => {
  console.error = originalConsoleError
  vi.clearAllMocks()
})
