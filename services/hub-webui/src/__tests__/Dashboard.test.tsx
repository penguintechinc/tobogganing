import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import Dashboard from '../pages/Dashboard'

// No auth dependency in Dashboard - it uses static data

describe('Dashboard page', () => {
  it('renders the page heading', () => {
    render(<Dashboard />)
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByText(/Overview of your Tobogganing hub network/i)).toBeInTheDocument()
  })

  it('renders all stat cards', () => {
    render(<Dashboard />)
    expect(screen.getByText('Hubs')).toBeInTheDocument()
    expect(screen.getByText('Connected Clients')).toBeInTheDocument()
    expect(screen.getByText('Active Policies')).toBeInTheDocument()
    expect(screen.getByText('Active Sessions')).toBeInTheDocument()
  })

  it('renders correct stat values', () => {
    render(<Dashboard />)
    // total_hubs: 4
    expect(screen.getByText('4')).toBeInTheDocument()
    // connected_clients: 112
    expect(screen.getByText('112')).toBeInTheDocument()
    // active_policies: 18
    expect(screen.getByText('18')).toBeInTheDocument()
    // active_sessions: 97
    expect(screen.getByText('97')).toBeInTheDocument()
  })

  it('renders subtitles with correct counts', () => {
    render(<Dashboard />)
    expect(screen.getByText('3 healthy')).toBeInTheDocument()
    expect(screen.getByText('of 128 total')).toBeInTheDocument()
    expect(screen.getByText('of 24 total')).toBeInTheDocument()
    expect(screen.getByText('Current connections')).toBeInTheDocument()
  })

  it('renders trend values', () => {
    render(<Dashboard />)
    expect(screen.getByText('100%')).toBeInTheDocument()
    expect(screen.getByText('+3')).toBeInTheDocument()
    expect(screen.getByText('+12')).toBeInTheDocument()
  })

  it('renders "vs last hour" trend labels', () => {
    render(<Dashboard />)
    const trendLabels = screen.getAllByText('vs last hour')
    expect(trendLabels.length).toBeGreaterThan(0)
  })

  it('renders hub status section', () => {
    render(<Dashboard />)
    expect(screen.getByText('Hub Status')).toBeInTheDocument()
  })

  it('renders all hub names in hub overview', () => {
    render(<Dashboard />)
    expect(screen.getByText('us-east-1')).toBeInTheDocument()
    expect(screen.getByText('us-west-2')).toBeInTheDocument()
    expect(screen.getByText('eu-west-1')).toBeInTheDocument()
    expect(screen.getByText('ap-south-1')).toBeInTheDocument()
  })

  it('renders hub capacity percentages', () => {
    render(<Dashboard />)
    expect(screen.getByText('68%')).toBeInTheDocument()
    expect(screen.getByText('55%')).toBeInTheDocument()
    expect(screen.getByText('82%')).toBeInTheDocument()
    expect(screen.getByText('0%')).toBeInTheDocument()
  })

  it('renders client counts in hub overview', () => {
    render(<Dashboard />)
    expect(screen.getByText('45 clients')).toBeInTheDocument()
    expect(screen.getByText('38 clients')).toBeInTheDocument()
    expect(screen.getByText('29 clients')).toBeInTheDocument()
    expect(screen.getByText('0 clients')).toBeInTheDocument()
  })

  it('renders recent activity section', () => {
    render(<Dashboard />)
    expect(screen.getByText('Recent Activity')).toBeInTheDocument()
  })

  it('renders recent activity items', () => {
    render(<Dashboard />)
    expect(screen.getByText(/Block Malicious Domains.*denied traffic/i)).toBeInTheDocument()
    expect(screen.getByText(/User admin@corp.io logged in/i)).toBeInTheDocument()
    expect(screen.getByText(/Hub us-east-1 health check passed/i)).toBeInTheDocument()
    expect(screen.getByText(/Policy.*Allow Internal DNS.*updated/i)).toBeInTheDocument()
    expect(screen.getByText(/Hub eu-west-1 capacity/i)).toBeInTheDocument()
  })

  it('renders activity timestamps', () => {
    render(<Dashboard />)
    expect(screen.getByText('2 min ago')).toBeInTheDocument()
    expect(screen.getByText('5 min ago')).toBeInTheDocument()
    expect(screen.getByText('8 min ago')).toBeInTheDocument()
    expect(screen.getByText('15 min ago')).toBeInTheDocument()
    expect(screen.getByText('22 min ago')).toBeInTheDocument()
  })

  describe('StatCard component (no trend)', () => {
    it('renders stat card without trend when not provided', () => {
      render(<Dashboard />)
      // Active Policies card has no trend
      expect(screen.getByText('Active Policies')).toBeInTheDocument()
      // The trend for that card is undefined, so no "vs last hour" text for it
      // Other cards do have it, just verifying render doesn't break
    })
  })

  describe('Hub status indicators', () => {
    it('renders degraded hub status', () => {
      render(<Dashboard />)
      // eu-west-1 is "degraded" - the dot is rendered
      expect(screen.getByText('eu-west-1')).toBeInTheDocument()
    })

    it('renders hub with zero capacity as 0%', () => {
      render(<Dashboard />)
      expect(screen.getByText('0%')).toBeInTheDocument()
    })
  })
})
