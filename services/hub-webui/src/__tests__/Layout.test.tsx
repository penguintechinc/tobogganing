import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'
import Layout from '../components/Layout'

vi.mock('../lib/auth', () => ({
  useAuth: vi.fn(),
}))

import { useAuth } from '../lib/auth'

const mockLogout = vi.fn()

function renderLayout(children = <div data-testid="child">Content</div>) {
  return render(
    <BrowserRouter>
      <Layout>{children}</Layout>
    </BrowserRouter>
  )
}

describe('Layout component', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: 'usr-001',
        email: 'admin@test.com',
        name: 'Test User',
        role: 'admin',
        created_at: '2025-01-01T00:00:00Z',
      },
      loading: false,
      login: vi.fn(),
      loginWithToken: vi.fn(),
      logout: mockLogout,
    })
  })

  it('renders children', () => {
    renderLayout()
    expect(screen.getByTestId('child')).toBeInTheDocument()
  })

  it('renders user name in header', () => {
    renderLayout()
    expect(screen.getByText('Test User')).toBeInTheDocument()
  })

  it('renders user role badge', () => {
    renderLayout()
    expect(screen.getByText('admin')).toBeInTheDocument()
  })

  it('renders Logout button', () => {
    renderLayout()
    expect(screen.getByRole('button', { name: /Logout/i })).toBeInTheDocument()
  })

  it('calls logout when Logout button clicked', async () => {
    mockLogout.mockResolvedValue(undefined)
    const user = userEvent.setup()
    renderLayout()

    await user.click(screen.getByRole('button', { name: /Logout/i }))

    expect(mockLogout).toHaveBeenCalledOnce()
  })

  it('renders sidebar with brand name', () => {
    renderLayout()
    // SidebarMenu renders Tobogganing brand in logo slot
    expect(screen.getByText('Tobogganing')).toBeInTheDocument()
  })

  it('renders with maintainer role user', () => {
    vi.mocked(useAuth).mockReturnValue({
      user: {
        id: 'usr-002',
        email: 'bob@test.com',
        name: 'Bob Smith',
        role: 'maintainer',
        created_at: '2025-01-01T00:00:00Z',
      },
      loading: false,
      login: vi.fn(),
      loginWithToken: vi.fn(),
      logout: mockLogout,
    })

    renderLayout()
    expect(screen.getByText('Bob Smith')).toBeInTheDocument()
    expect(screen.getByText('maintainer')).toBeInTheDocument()
  })

})
