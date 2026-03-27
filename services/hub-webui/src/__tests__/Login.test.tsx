import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'
import Login from '../pages/Login'

vi.mock('../lib/auth', () => ({
  useAuth: vi.fn(),
}))

import { useAuth } from '../lib/auth'

const mockLogin = vi.fn()

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
      login: mockLogin,
      logout: vi.fn(),
    })
  })

  it('renders the login form with all required elements', () => {
    renderLogin()
    expect(screen.getByText('Tobogganing')).toBeInTheDocument()
    expect(screen.getByText('Hub Management Console')).toBeInTheDocument()
    // "Sign In" appears as both h2 heading and button — check for both
    expect(screen.getAllByText('Sign In').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument()
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument()
  })

  it('shows Penguin Tech branding at the bottom', () => {
    renderLogin()
    expect(screen.getByText(/Powered by Penguin Tech Inc/i)).toBeInTheDocument()
  })

  it('email input has correct type and attributes', () => {
    renderLogin()
    const emailInput = screen.getByLabelText(/email/i)
    expect(emailInput).toHaveAttribute('type', 'email')
    expect(emailInput).toHaveAttribute('required')
    expect(emailInput).toHaveAttribute('autocomplete', 'email')
  })

  it('password input has correct type and attributes', () => {
    renderLogin()
    const passwordInput = screen.getByLabelText(/password/i)
    expect(passwordInput).toHaveAttribute('type', 'password')
    expect(passwordInput).toHaveAttribute('required')
    expect(passwordInput).toHaveAttribute('autocomplete', 'current-password')
  })

  it('calls login with email and password on form submit', async () => {
    mockLogin.mockResolvedValue(undefined)
    const user = userEvent.setup()
    renderLogin()

    await user.type(screen.getByLabelText(/email/i), 'admin@test.com')
    await user.type(screen.getByLabelText(/password/i), 'password123')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(mockLogin).toHaveBeenCalledWith('admin@test.com', 'password123')
    })
  })

  it('shows loading state while submitting', async () => {
    // login never resolves so we can check loading state
    mockLogin.mockImplementation(() => new Promise(() => {}))
    const user = userEvent.setup()
    renderLogin()

    await user.type(screen.getByLabelText(/email/i), 'admin@test.com')
    await user.type(screen.getByLabelText(/password/i), 'password123')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(screen.getByRole('button', { name: /signing in/i })).toBeInTheDocument()
    })
    expect(screen.getByRole('button', { name: /signing in/i })).toBeDisabled()
  })

  it('shows error message on login failure', async () => {
    mockLogin.mockRejectedValue(new Error('Invalid credentials'))
    const user = userEvent.setup()
    renderLogin()

    await user.type(screen.getByLabelText(/email/i), 'bad@test.com')
    await user.type(screen.getByLabelText(/password/i), 'wrongpass')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(screen.getByText(/Invalid email or password/i)).toBeInTheDocument()
    })
  })

  it('clears error on new submission attempt', async () => {
    mockLogin.mockRejectedValueOnce(new Error('Invalid credentials'))
    mockLogin.mockResolvedValueOnce(undefined)
    const user = userEvent.setup()
    renderLogin()

    await user.type(screen.getByLabelText(/email/i), 'bad@test.com')
    await user.type(screen.getByLabelText(/password/i), 'wrongpass')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      expect(screen.getByText(/Invalid email or password/i)).toBeInTheDocument()
    })

    // Try again - error should clear
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    // While submitting, error disappears
    await waitFor(() => {
      expect(screen.queryByText(/Invalid email or password/i)).not.toBeInTheDocument()
    })
  })

  it('button is re-enabled after failed submission', async () => {
    mockLogin.mockRejectedValue(new Error('Invalid credentials'))
    const user = userEvent.setup()
    renderLogin()

    await user.type(screen.getByLabelText(/email/i), 'bad@test.com')
    await user.type(screen.getByLabelText(/password/i), 'wrongpass')
    await user.click(screen.getByRole('button', { name: /sign in/i }))

    await waitFor(() => {
      const btn = screen.getByRole('button', { name: /sign in/i })
      expect(btn).not.toBeDisabled()
    })
  })

  it('updates email field value as user types', async () => {
    const user = userEvent.setup()
    renderLogin()

    const emailInput = screen.getByLabelText(/email/i)
    await user.type(emailInput, 'hello@world.com')
    expect(emailInput).toHaveValue('hello@world.com')
  })

  it('updates password field value as user types', async () => {
    const user = userEvent.setup()
    renderLogin()

    const passwordInput = screen.getByLabelText(/password/i)
    await user.type(passwordInput, 'mypassword')
    expect(passwordInput).toHaveValue('mypassword')
  })
})
