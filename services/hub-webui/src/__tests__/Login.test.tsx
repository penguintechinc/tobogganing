import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { BrowserRouter } from 'react-router-dom'
import Login from '../pages/Login'

vi.mock('../lib/auth', () => ({
  useAuth: vi.fn(),
}))

// LoginPageBuilder from react-libs renders the full login form
// Mock it to keep tests focused on the Login page wrapper
vi.mock('@penguintechinc/react-libs', () => ({
  LoginPageBuilder: ({
    branding,
    onSuccess,
  }: {
    branding: { appName: string; tagline?: string }
    onSuccess: (r: { token?: string; user?: { id: string; email: string; name?: string; roles?: string[] } }) => void
  }) => (
    <div data-testid="login-page-builder">
      <div data-testid="app-name">{branding.appName}</div>
      {branding.tagline && <div data-testid="tagline">{branding.tagline}</div>}
      <button
        data-testid="mock-success-btn"
        onClick={() =>
          onSuccess({
            token: 'test-token',
            user: { id: 'u1', email: 'admin@test.com', name: 'Admin', roles: ['admin'] },
          })
        }
      >
        Trigger Success
      </button>
    </div>
  ),
}))

import { useAuth } from '../lib/auth'

const mockLoginWithToken = vi.fn()

function renderLogin() {
  return render(
    <BrowserRouter>
      <Login />
    </BrowserRouter>
  )
}

describe('Login page', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useAuth).mockReturnValue({
      user: null,
      loading: false,
      login: vi.fn(),
      loginWithToken: mockLoginWithToken,
      logout: vi.fn(),
    })
  })

  it('renders LoginPageBuilder', () => {
    renderLogin()
    expect(screen.getByTestId('login-page-builder')).toBeInTheDocument()
  })

  it('passes correct app name to LoginPageBuilder', () => {
    renderLogin()
    expect(screen.getByTestId('app-name')).toHaveTextContent('Tobogganing')
  })

  it('passes correct tagline to LoginPageBuilder', () => {
    renderLogin()
    expect(screen.getByTestId('tagline')).toHaveTextContent('Hub Management Console')
  })

  it('calls loginWithToken on successful login', async () => {
    const { getByTestId } = renderLogin()
    getByTestId('mock-success-btn').click()

    expect(mockLoginWithToken).toHaveBeenCalledWith(
      'test-token',
      expect.objectContaining({
        id: 'u1',
        email: 'admin@test.com',
        name: 'Admin',
        role: 'admin',
      })
    )
  })

  it('maps first role from roles array to role field', async () => {
    const { getByTestId } = renderLogin()
    getByTestId('mock-success-btn').click()

    expect(mockLoginWithToken).toHaveBeenCalledWith(
      'test-token',
      expect.objectContaining({ role: 'admin' })
    )
  })
})
