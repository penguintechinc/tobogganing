import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import App from '../App'

vi.mock('../lib/auth', () => ({
  useAuth: vi.fn(),
  ProtectedRoute: ({ children }: { children: React.ReactNode }) => <>{children}</>,
  AuthProvider: ({ children }: { children: React.ReactNode }) => <>{children}</>,
}))

// Mock all pages to keep the test focused on routing
vi.mock('../pages/Login', () => ({
  default: () => <div data-testid="login-page">Login Page</div>,
}))
vi.mock('../pages/Dashboard', () => ({
  default: () => <div data-testid="dashboard-page">Dashboard</div>,
}))
vi.mock('../pages/PolicyManagement', () => ({
  default: () => <div data-testid="policy-page">Policies</div>,
}))
vi.mock('../pages/ClientManagement', () => ({
  default: () => <div data-testid="client-page">Clients</div>,
}))
vi.mock('../pages/HubManagement', () => ({
  default: () => <div data-testid="hub-page">Hubs</div>,
}))
vi.mock('../pages/UserManagement', () => ({
  default: () => <div data-testid="user-page">Users</div>,
}))
vi.mock('../pages/IdentityProviders', () => ({
  default: () => <div data-testid="identity-page">Identity</div>,
}))
vi.mock('../pages/Settings', () => ({
  default: () => <div data-testid="settings-page">Settings</div>,
}))
vi.mock('../pages/AuditLogs', () => ({
  default: () => <div data-testid="audit-page">Audit Logs</div>,
}))
vi.mock('../components/Layout', () => ({
  default: ({ children }: { children: React.ReactNode }) => <div data-testid="layout">{children}</div>,
}))

import { useAuth } from '../lib/auth'

const mockUser = {
  id: 'usr-001',
  email: 'admin@test.com',
  name: 'Test Admin',
  role: 'admin' as const,
  created_at: '2025-01-01T00:00:00Z',
}

function renderApp(initialPath: string) {
  return render(
    <MemoryRouter initialEntries={[initialPath]}>
      <App />
    </MemoryRouter>
  )
}

describe('App routing — unauthenticated', () => {
  beforeEach(() => {
    vi.mocked(useAuth).mockReturnValue({
      user: null,
      loading: false,
      login: vi.fn(),
      logout: vi.fn(),
    })
  })

  it('renders Login page on /login route when unauthenticated', () => {
    renderApp('/login')
    expect(screen.getByTestId('login-page')).toBeInTheDocument()
  })

  it('redirects to /login from / when unauthenticated', () => {
    renderApp('/')
    // The Navigate redirects to /login which renders Login page
    expect(screen.getByTestId('login-page')).toBeInTheDocument()
  })

  it('redirects to /login from any unknown path when unauthenticated', () => {
    renderApp('/some-unknown-path')
    expect(screen.getByTestId('login-page')).toBeInTheDocument()
  })

  it('redirects /policies to /login when unauthenticated', () => {
    renderApp('/policies')
    expect(screen.getByTestId('login-page')).toBeInTheDocument()
  })
})

describe('App routing — authenticated', () => {
  beforeEach(() => {
    vi.mocked(useAuth).mockReturnValue({
      user: mockUser,
      loading: false,
      login: vi.fn(),
      logout: vi.fn(),
    })
  })

  it('renders Dashboard at / when authenticated', () => {
    renderApp('/')
    expect(screen.getByTestId('dashboard-page')).toBeInTheDocument()
    expect(screen.getByTestId('layout')).toBeInTheDocument()
  })

  it('renders PolicyManagement at /policies', () => {
    renderApp('/policies')
    expect(screen.getByTestId('policy-page')).toBeInTheDocument()
  })

  it('renders ClientManagement at /clients', () => {
    renderApp('/clients')
    expect(screen.getByTestId('client-page')).toBeInTheDocument()
  })

  it('renders HubManagement at /hubs', () => {
    renderApp('/hubs')
    expect(screen.getByTestId('hub-page')).toBeInTheDocument()
  })

  it('renders UserManagement at /users', () => {
    renderApp('/users')
    expect(screen.getByTestId('user-page')).toBeInTheDocument()
  })

  it('renders IdentityProviders at /identity', () => {
    renderApp('/identity')
    expect(screen.getByTestId('identity-page')).toBeInTheDocument()
  })

  it('renders Settings at /settings', () => {
    renderApp('/settings')
    expect(screen.getByTestId('settings-page')).toBeInTheDocument()
  })

  it('renders AuditLogs at /audit', () => {
    renderApp('/audit')
    expect(screen.getByTestId('audit-page')).toBeInTheDocument()
  })

  it('redirects /login to / when authenticated', () => {
    renderApp('/login')
    expect(screen.getByTestId('dashboard-page')).toBeInTheDocument()
  })

  it('redirects unknown paths to / when authenticated', () => {
    renderApp('/some-unknown-route')
    expect(screen.getByTestId('dashboard-page')).toBeInTheDocument()
  })

  it('wraps authenticated routes in Layout', () => {
    renderApp('/')
    expect(screen.getByTestId('layout')).toBeInTheDocument()
  })
})
