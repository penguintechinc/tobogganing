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

  it('renders sidebar', () => {
    renderLayout()
    // Sidebar renders the Tobogganing title
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
      logout: mockLogout,
    })

    renderLayout()
    expect(screen.getByText('Bob Smith')).toBeInTheDocument()
    expect(screen.getByText('maintainer')).toBeInTheDocument()
  })

  it('collapses sidebar when toggle button clicked', async () => {
    const user = userEvent.setup()
    renderLayout()

    // The collapse button in Sidebar
    const collapseBtn = screen.getByRole('button', { name: /Collapse sidebar/i })
    await user.click(collapseBtn)

    // After collapsing, the expand button appears
    expect(screen.getByRole('button', { name: /Expand sidebar/i })).toBeInTheDocument()
    // The title should be hidden
    expect(screen.queryByText('Tobogganing')).not.toBeInTheDocument()
  })

  it('expands sidebar when expand button clicked after collapse', async () => {
    const user = userEvent.setup()
    renderLayout()

    // Collapse
    await user.click(screen.getByRole('button', { name: /Collapse sidebar/i }))
    expect(screen.queryByText('Tobogganing')).not.toBeInTheDocument()

    // Expand
    await user.click(screen.getByRole('button', { name: /Expand sidebar/i }))
    expect(screen.getByText('Tobogganing')).toBeInTheDocument()
  })
})
