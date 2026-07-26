import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import Settings from '../pages/Settings'

describe('Settings page', () => {
  it('renders the page heading', () => {
    render(<Settings />)
    expect(screen.getByText('Settings')).toBeInTheDocument()
    expect(screen.getByText(/Configure your Tobogganing hub deployment/i)).toBeInTheDocument()
  })

  it('renders all tab buttons', () => {
    render(<Settings />)
    expect(screen.getByRole('button', { name: /General/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Security/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Notifications/i })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /Advanced/i })).toBeInTheDocument()
  })

  it('shows General settings by default', () => {
    render(<Settings />)
    expect(screen.getByText('General Settings')).toBeInTheDocument()
    // Labels don't have htmlFor — check their text content directly
    expect(screen.getByText('Deployment Name')).toBeInTheDocument()
    expect(screen.getByText('Admin Contact Email')).toBeInTheDocument()
    expect(screen.getByText('Default Hub Region')).toBeInTheDocument()
  })

  it('renders general settings with default values', () => {
    render(<Settings />)
    expect(screen.getByDisplayValue('Production Hub')).toBeInTheDocument()
    expect(screen.getByDisplayValue('admin@corp.io')).toBeInTheDocument()
  })

  it('renders region select options', () => {
    render(<Settings />)
    expect(screen.getByText('US East (Virginia)')).toBeInTheDocument()
    expect(screen.getByText('US West (Oregon)')).toBeInTheDocument()
    expect(screen.getByText('EU West (Ireland)')).toBeInTheDocument()
    expect(screen.getByText('AP South (Mumbai)')).toBeInTheDocument()
  })

  it('switches to Security tab on click', async () => {
    const user = userEvent.setup()
    render(<Settings />)

    await user.click(screen.getByRole('button', { name: /Security/i }))

    expect(screen.getByText('Security Settings')).toBeInTheDocument()
    expect(screen.getByText('Enforce MFA for Admins')).toBeInTheDocument()
    expect(screen.getByText('Session Timeout')).toBeInTheDocument()
    expect(screen.getByText('API Rate Limiting')).toBeInTheDocument()
    expect(screen.getByText('TLS Minimum Version')).toBeInTheDocument()
  })

  it('renders Security tab content correctly', async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole('button', { name: /Security/i }))

    expect(screen.getByText('Require multi-factor authentication for admin accounts')).toBeInTheDocument()
    expect(screen.getByText('Automatically log out inactive users')).toBeInTheDocument()
    expect(screen.getByText('Maximum API requests per minute per user')).toBeInTheDocument()
    expect(screen.getByText('Minimum TLS version for client connections')).toBeInTheDocument()
  })

  it('renders API rate limit input in Security tab', async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole('button', { name: /Security/i }))

    const rateInput = screen.getByDisplayValue('100')
    expect(rateInput).toBeInTheDocument()
    expect(rateInput).toHaveAttribute('type', 'number')
  })

  it('renders TLS version options', async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole('button', { name: /Security/i }))

    expect(screen.getByText('TLS 1.3')).toBeInTheDocument()
    expect(screen.getByText('TLS 1.2')).toBeInTheDocument()
  })

  it('switches to Notifications tab on click', async () => {
    const user = userEvent.setup()
    render(<Settings />)

    await user.click(screen.getByRole('button', { name: /Notifications/i }))

    expect(screen.getByText('Notification Settings')).toBeInTheDocument()
    expect(screen.getByText('Hub Offline Alerts')).toBeInTheDocument()
    expect(screen.getByText('Capacity Warnings')).toBeInTheDocument()
    expect(screen.getByText('Policy Violations')).toBeInTheDocument()
    expect(screen.getByText('User Login Events')).toBeInTheDocument()
  })

  it('renders notification toggle states', async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole('button', { name: /Notifications/i }))

    const enabledBadges = screen.getAllByText('Enabled')
    const disabledBadges = screen.getAllByText('Disabled')
    expect(enabledBadges.length).toBe(2) // Hub Offline Alerts, Capacity Warnings
    expect(disabledBadges.length).toBe(2) // Policy Violations, User Login Events
  })

  it('renders webhook URL input in Notifications tab', async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole('button', { name: /Notifications/i }))

    const webhookInput = screen.getByPlaceholderText(/https:\/\/hooks\.slack\.com/i)
    expect(webhookInput).toBeInTheDocument()
    expect(webhookInput).toHaveAttribute('type', 'url')
  })

  it('switches to Advanced tab on click', async () => {
    const user = userEvent.setup()
    render(<Settings />)

    await user.click(screen.getByRole('button', { name: /Advanced/i }))

    expect(screen.getByText('Advanced Settings')).toBeInTheDocument()
    // Labels don't have htmlFor — check their text content directly
    expect(screen.getByText('Log Level')).toBeInTheDocument()
    expect(screen.getByText('Data Retention (days)')).toBeInTheDocument()
    expect(screen.getByText('Max Clients Per Hub')).toBeInTheDocument()
  })

  it('renders Advanced tab with default values', async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole('button', { name: /Advanced/i }))

    expect(screen.getByDisplayValue('90')).toBeInTheDocument()
    expect(screen.getByDisplayValue('100')).toBeInTheDocument()
  })

  it('renders log level options', async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole('button', { name: /Advanced/i }))

    expect(screen.getByText('info')).toBeInTheDocument()
    expect(screen.getByText('debug')).toBeInTheDocument()
    expect(screen.getByText('warn')).toBeInTheDocument()
    expect(screen.getByText('error')).toBeInTheDocument()
  })

  it('renders data retention note', async () => {
    const user = userEvent.setup()
    render(<Settings />)
    await user.click(screen.getByRole('button', { name: /Advanced/i }))

    expect(screen.getByText(/Audit logs and session data older than this will be purged/i)).toBeInTheDocument()
  })

  it('renders Save Changes button on all tabs', async () => {
    const user = userEvent.setup()
    render(<Settings />)

    // General
    expect(screen.getByRole('button', { name: /Save Changes/i })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Security/i }))
    expect(screen.getByRole('button', { name: /Save Changes/i })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Notifications/i }))
    expect(screen.getByRole('button', { name: /Save Changes/i })).toBeInTheDocument()

    await user.click(screen.getByRole('button', { name: /Advanced/i }))
    expect(screen.getByRole('button', { name: /Save Changes/i })).toBeInTheDocument()
  })

  it('highlights active tab', async () => {
    const user = userEvent.setup()
    render(<Settings />)

    // General is active by default
    const generalBtn = screen.getByRole('button', { name: /General/i })
    expect(generalBtn.className).toContain('text-text-gold')

    // Switch to Security
    await user.click(screen.getByRole('button', { name: /Security/i }))
    const securityBtn = screen.getByRole('button', { name: /Security/i })
    expect(securityBtn.className).toContain('text-text-gold')
  })

  it('hides inactive tabs content', async () => {
    const user = userEvent.setup()
    render(<Settings />)

    // Switch to Security - General content should be gone
    await user.click(screen.getByRole('button', { name: /Security/i }))
    expect(screen.queryByText('General Settings')).not.toBeInTheDocument()

    // Switch to Notifications - Security content should be gone
    await user.click(screen.getByRole('button', { name: /Notifications/i }))
    expect(screen.queryByText('Security Settings')).not.toBeInTheDocument()

    // Switch to Advanced - Notifications content should be gone
    await user.click(screen.getByRole('button', { name: /Advanced/i }))
    expect(screen.queryByText('Notification Settings')).not.toBeInTheDocument()
  })
})
