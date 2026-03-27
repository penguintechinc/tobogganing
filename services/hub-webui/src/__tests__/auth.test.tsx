import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { render, screen, waitFor, act } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'
import { AuthProvider, useAuth, ProtectedRoute } from '../lib/auth'
import type { ReactNode } from 'react'

// Mock the api module
vi.mock('../lib/api', () => ({
  authApi: {
    login: vi.fn(),
    logout: vi.fn(),
    me: vi.fn(),
    refresh: vi.fn(),
  },
}))

import { authApi } from '../lib/api'

const mockUser = {
  id: 'usr-001',
  email: 'admin@test.com',
  name: 'Test Admin',
  role: 'admin' as const,
  created_at: '2025-01-01T00:00:00Z',
}

const mockAuthResponse = {
  token: 'test-jwt-token',
  user: mockUser,
}

function TestConsumer() {
  const { user, loading, login, logout } = useAuth()
  return (
    <div>
      <div data-testid="loading">{loading.toString()}</div>
      <div data-testid="user">{user ? user.email : 'null'}</div>
      <button onClick={() => login('test@test.com', 'pass')} data-testid="login-btn">Login</button>
      <button onClick={() => logout().catch(() => {})} data-testid="logout-btn">Logout</button>
    </div>
  )
}

function renderWithRouter(ui: ReactNode) {
  return render(<BrowserRouter>{ui}</BrowserRouter>)
}

describe('AuthProvider', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('renders loading state initially when token exists', async () => {
    localStorage.setItem('tobogganing_token', 'existing-token')
    vi.mocked(authApi.me).mockResolvedValue(mockUser)

    renderWithRouter(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    )

    // Initially loads
    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })
    expect(screen.getByTestId('user').textContent).toBe('admin@test.com')
  })

  it('sets loading to false with no user when no token exists', async () => {
    renderWithRouter(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })
    expect(screen.getByTestId('user').textContent).toBe('null')
  })

  it('clears token and user when me() call fails', async () => {
    localStorage.setItem('tobogganing_token', 'bad-token')
    vi.mocked(authApi.me).mockRejectedValue(new Error('401 Unauthorized'))

    renderWithRouter(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('user').textContent).toBe('null')
    })
    expect(localStorage.getItem('tobogganing_token')).toBeNull()
  })

  it('shows loading spinner when auth is loading', async () => {
    localStorage.setItem('tobogganing_token', 'token')
    // me() never resolves to keep loading state
    vi.mocked(authApi.me).mockImplementation(() => new Promise(() => {}))

    renderWithRouter(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    )

    // Should show loading spinner (not the TestConsumer)
    expect(screen.getByText('Loading...')).toBeInTheDocument()
  })

  it('login sets user and stores token', async () => {
    vi.mocked(authApi.login).mockResolvedValue(mockAuthResponse)

    renderWithRouter(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('loading').textContent).toBe('false')
    })

    await userEvent.click(screen.getByTestId('login-btn'))

    // The user email shown is from the response, not the input
    await waitFor(() => {
      expect(screen.getByTestId('user').textContent).toBe('admin@test.com')
    })
    expect(localStorage.getItem('tobogganing_token')).toBe('test-jwt-token')
  })

  it('logout clears user and token', async () => {
    localStorage.setItem('tobogganing_token', 'token')
    vi.mocked(authApi.me).mockResolvedValue(mockUser)
    vi.mocked(authApi.logout).mockResolvedValue(undefined)

    renderWithRouter(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('user').textContent).toBe('admin@test.com')
    })

    await userEvent.click(screen.getByTestId('logout-btn'))

    await waitFor(() => {
      expect(screen.getByTestId('user').textContent).toBe('null')
    })
    expect(localStorage.getItem('tobogganing_token')).toBeNull()
  })

  it('logout clears user even if API call fails', async () => {
    localStorage.setItem('tobogganing_token', 'token')
    vi.mocked(authApi.me).mockResolvedValue(mockUser)
    vi.mocked(authApi.logout).mockRejectedValue(new Error('Network error'))

    renderWithRouter(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('user').textContent).toBe('admin@test.com')
    })

    // The logout button handler catches the error, so click completes normally
    await userEvent.click(screen.getByTestId('logout-btn'))

    // The logout function uses try/finally so it should clear user even on error
    await waitFor(() => {
      expect(screen.getByTestId('user').textContent).toBe('null')
    })
    expect(localStorage.getItem('tobogganing_token')).toBeNull()
  })
})

describe('useAuth', () => {
  it('throws when used outside AuthProvider', () => {
    // Suppress the error output from the expected throw
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})

    expect(() => {
      render(
        <BrowserRouter>
          <TestConsumer />
        </BrowserRouter>
      )
    }).toThrow('useAuth must be used within an AuthProvider')

    spy.mockRestore()
  })
})

describe('ProtectedRoute', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
  })

  it('renders children when user is authenticated', async () => {
    localStorage.setItem('tobogganing_token', 'token')
    vi.mocked(authApi.me).mockResolvedValue(mockUser)

    renderWithRouter(
      <AuthProvider>
        <ProtectedRoute>
          <div data-testid="protected-content">Secret Content</div>
        </ProtectedRoute>
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.getByTestId('protected-content')).toBeInTheDocument()
    })
  })

  it('returns null while loading', async () => {
    localStorage.setItem('tobogganing_token', 'token')
    vi.mocked(authApi.me).mockImplementation(() => new Promise(() => {}))

    renderWithRouter(
      <AuthProvider>
        <ProtectedRoute>
          <div data-testid="protected-content">Secret</div>
        </ProtectedRoute>
      </AuthProvider>
    )

    // Loading spinner is shown by AuthProvider, not ProtectedRoute
    expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument()
  })

  it('redirects to login when no user', async () => {
    renderWithRouter(
      <AuthProvider>
        <ProtectedRoute>
          <div data-testid="protected-content">Secret</div>
        </ProtectedRoute>
      </AuthProvider>
    )

    await waitFor(() => {
      expect(screen.queryByTestId('protected-content')).not.toBeInTheDocument()
    })
  })
})

describe('Token refresh', () => {
  beforeEach(() => {
    localStorage.clear()
    vi.clearAllMocks()
    // Use fake timers but allow real-time advancing for microtasks/promises
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  it('schedules token refresh when user is logged in', async () => {
    localStorage.setItem('tobogganing_token', 'token')
    vi.mocked(authApi.me).mockResolvedValue(mockUser)
    vi.mocked(authApi.refresh).mockResolvedValue({
      token: 'new-token',
      user: mockUser,
    })

    renderWithRouter(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    )

    // Wait for the initial me() call to resolve (real-time promises work with shouldAdvanceTime)
    await waitFor(() => {
      expect(screen.getByTestId('user').textContent).toBe('admin@test.com')
    })

    // Advance timer past 14 minutes and let the refresh promise settle
    await act(async () => {
      vi.advanceTimersByTime(14 * 60 * 1000 + 1000)
    })

    // Give the refresh promise time to resolve
    await act(async () => {
      await Promise.resolve()
    })

    expect(authApi.refresh).toHaveBeenCalled()
    expect(localStorage.getItem('tobogganing_token')).toBe('new-token')
  }, 15000)

  it('logs out when refresh fails', async () => {
    localStorage.setItem('tobogganing_token', 'token')
    vi.mocked(authApi.me).mockResolvedValue(mockUser)
    vi.mocked(authApi.refresh).mockRejectedValue(new Error('Token expired'))

    renderWithRouter(
      <AuthProvider>
        <TestConsumer />
      </AuthProvider>
    )

    // Wait for the initial me() call to resolve
    await waitFor(() => {
      expect(screen.getByTestId('user').textContent).toBe('admin@test.com')
    })

    // Advance timer past 14 minutes
    await act(async () => {
      vi.advanceTimersByTime(14 * 60 * 1000 + 1000)
    })

    // Give the refresh rejection handler time to run
    await act(async () => {
      await Promise.resolve()
    })

    expect(screen.getByTestId('user').textContent).toBe('null')
    expect(localStorage.getItem('tobogganing_token')).toBeNull()
  }, 15000)
})
