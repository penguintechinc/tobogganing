import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import ClientManagement from '../pages/ClientManagement'

describe('ClientManagement page', () => {
  it('renders the page heading', () => {
    render(<ClientManagement />)
    expect(screen.getByText('Clients')).toBeInTheDocument()
    expect(screen.getByText(/Manage connected clients and their hub assignments/i)).toBeInTheDocument()
  })

  it('renders all status filter cards', () => {
    render(<ClientManagement />)
    expect(screen.getByText('Total')).toBeInTheDocument()
    expect(screen.getByText('Connected')).toBeInTheDocument()
    expect(screen.getByText('Disconnected')).toBeInTheDocument()
    expect(screen.getByText('Pending')).toBeInTheDocument()
  })

  it('renders correct status counts', () => {
    render(<ClientManagement />)
    // All: 5, Connected: 3, Disconnected: 1, Pending: 1
    const countElements = screen.getAllByText('5')
    expect(countElements.length).toBeGreaterThan(0)
  })

  it('renders search input', () => {
    render(<ClientManagement />)
    expect(screen.getByPlaceholderText(/Search by name, hostname, or IP/i)).toBeInTheDocument()
  })

  it('renders Refresh button', () => {
    render(<ClientManagement />)
    expect(screen.getByRole('button', { name: /Refresh/i })).toBeInTheDocument()
  })

  it('renders all mock clients', () => {
    render(<ClientManagement />)
    expect(screen.getByText('dev-laptop-alice')).toBeInTheDocument()
    expect(screen.getByText('server-prod-web01')).toBeInTheDocument()
    expect(screen.getByText('dev-laptop-bob')).toBeInTheDocument()
    expect(screen.getByText('iot-sensor-floor3')).toBeInTheDocument()
    expect(screen.getByText('staging-api-gateway')).toBeInTheDocument()
  })

  it('renders client hostnames', () => {
    render(<ClientManagement />)
    expect(screen.getByText('alice-mbp.local')).toBeInTheDocument()
    expect(screen.getByText('web01.prod.internal')).toBeInTheDocument()
    expect(screen.getByText('bob-thinkpad.local')).toBeInTheDocument()
  })

  it('renders client IP addresses', () => {
    render(<ClientManagement />)
    expect(screen.getByText('10.0.1.15')).toBeInTheDocument()
    expect(screen.getByText('10.0.2.50')).toBeInTheDocument()
    expect(screen.getByText('10.0.1.22')).toBeInTheDocument()
  })

  it('renders client version tags', () => {
    render(<ClientManagement />)
    const v142 = screen.getAllByText('v1.4.2')
    expect(v142.length).toBeGreaterThan(0)
    expect(screen.getByText('v1.4.1')).toBeInTheDocument()
    expect(screen.getByText('v1.3.8')).toBeInTheDocument()
  })

  it('renders client status badges', () => {
    render(<ClientManagement />)
    const connectedBadges = screen.getAllByText('connected')
    const disconnectedBadges = screen.getAllByText('disconnected')
    const pendingBadges = screen.getAllByText('pending')
    expect(connectedBadges.length).toBe(3)
    expect(disconnectedBadges.length).toBe(1)
    expect(pendingBadges.length).toBe(1)
  })

  it('renders hub assignments for clients', () => {
    render(<ClientManagement />)
    // Multiple clients can be assigned to the same hub, use getAllByText
    expect(screen.getAllByText('us-east-1').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('us-west-2').length).toBeGreaterThanOrEqual(1)
  })

  it('shows Hub Assignments label for clients with hubs', () => {
    render(<ClientManagement />)
    const hubLabels = screen.getAllByText('Hub Assignments')
    expect(hubLabels.length).toBeGreaterThan(0)
  })

  it('does not show Hub Assignments for clients with no hubs', () => {
    render(<ClientManagement />)
    // staging-api-gateway has empty hub_ids
    // Only 4 clients have hub assignments (not staging-api-gateway)
    const hubLabels = screen.getAllByText('Hub Assignments')
    expect(hubLabels.length).toBe(4)
  })

  describe('Search functionality', () => {
    it('filters clients by name', async () => {
      const user = userEvent.setup()
      render(<ClientManagement />)

      await user.type(screen.getByPlaceholderText(/Search/i), 'alice')

      expect(screen.getByText('dev-laptop-alice')).toBeInTheDocument()
      expect(screen.queryByText('dev-laptop-bob')).not.toBeInTheDocument()
      expect(screen.queryByText('server-prod-web01')).not.toBeInTheDocument()
    })

    it('filters clients by hostname', async () => {
      const user = userEvent.setup()
      render(<ClientManagement />)

      await user.type(screen.getByPlaceholderText(/Search/i), 'prod.internal')

      expect(screen.getByText('server-prod-web01')).toBeInTheDocument()
      expect(screen.queryByText('dev-laptop-alice')).not.toBeInTheDocument()
    })

    it('filters clients by IP address', async () => {
      const user = userEvent.setup()
      render(<ClientManagement />)

      await user.type(screen.getByPlaceholderText(/Search/i), '10.0.2')

      expect(screen.getByText('server-prod-web01')).toBeInTheDocument()
      expect(screen.queryByText('dev-laptop-alice')).not.toBeInTheDocument()
    })

    it('shows empty state when no clients match search', async () => {
      const user = userEvent.setup()
      render(<ClientManagement />)

      await user.type(screen.getByPlaceholderText(/Search/i), 'nonexistentclient12345')

      expect(screen.getByText('No clients match your search')).toBeInTheDocument()
    })

    it('search is case-insensitive', async () => {
      const user = userEvent.setup()
      render(<ClientManagement />)

      await user.type(screen.getByPlaceholderText(/Search/i), 'ALICE')

      expect(screen.getByText('dev-laptop-alice')).toBeInTheDocument()
    })
  })

  describe('Status filter', () => {
    it('filters to connected clients only', async () => {
      const user = userEvent.setup()
      render(<ClientManagement />)

      await user.click(screen.getByText('Connected'))

      // connected clients: alice, web01, iot-sensor
      expect(screen.getByText('dev-laptop-alice')).toBeInTheDocument()
      expect(screen.getByText('server-prod-web01')).toBeInTheDocument()
      expect(screen.getByText('iot-sensor-floor3')).toBeInTheDocument()
      expect(screen.queryByText('dev-laptop-bob')).not.toBeInTheDocument()
      expect(screen.queryByText('staging-api-gateway')).not.toBeInTheDocument()
    })

    it('filters to disconnected clients only', async () => {
      const user = userEvent.setup()
      render(<ClientManagement />)

      await user.click(screen.getByText('Disconnected'))

      expect(screen.getByText('dev-laptop-bob')).toBeInTheDocument()
      expect(screen.queryByText('dev-laptop-alice')).not.toBeInTheDocument()
    })

    it('filters to pending clients only', async () => {
      const user = userEvent.setup()
      render(<ClientManagement />)

      await user.click(screen.getByText('Pending'))

      expect(screen.getByText('staging-api-gateway')).toBeInTheDocument()
      expect(screen.queryByText('dev-laptop-alice')).not.toBeInTheDocument()
    })

    it('shows all clients when All filter is clicked', async () => {
      const user = userEvent.setup()
      render(<ClientManagement />)

      // First filter to connected
      await user.click(screen.getByText('Connected'))
      expect(screen.queryByText('dev-laptop-bob')).not.toBeInTheDocument()

      // Then click All
      await user.click(screen.getByText('Total'))
      expect(screen.getByText('dev-laptop-bob')).toBeInTheDocument()
    })

    it('highlights the active filter button', async () => {
      const user = userEvent.setup()
      render(<ClientManagement />)

      await user.click(screen.getByText('Connected'))

      // The Connected button should have accent class, others should not
      // This tests the clsx logic for statusFilter
      const connectedBtn = screen.getByText('Connected').closest('button')!
      expect(connectedBtn.className).toContain('border-accent')
    })
  })

  describe('Combined search and filter', () => {
    it('applies both search and status filter simultaneously', async () => {
      const user = userEvent.setup()
      render(<ClientManagement />)

      // Filter to connected and search for alice
      await user.click(screen.getByText('Connected'))
      await user.type(screen.getByPlaceholderText(/Search/i), 'alice')

      expect(screen.getByText('dev-laptop-alice')).toBeInTheDocument()
      expect(screen.queryByText('server-prod-web01')).not.toBeInTheDocument()
    })
  })
})
