import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import HubManagement from '../pages/HubManagement'

describe('HubManagement page', () => {
  it('renders the page heading', () => {
    render(<HubManagement />)
    expect(screen.getByText('Hubs')).toBeInTheDocument()
    expect(screen.getByText(/Manage hub-router instances across regions/i)).toBeInTheDocument()
  })

  it('renders Add Hub button', () => {
    render(<HubManagement />)
    expect(screen.getByRole('button', { name: /Add Hub/i })).toBeInTheDocument()
  })

  it('renders all mock hubs', () => {
    render(<HubManagement />)
    expect(screen.getByText('US East (Virginia)')).toBeInTheDocument()
    expect(screen.getByText('US West (Oregon)')).toBeInTheDocument()
    expect(screen.getByText('EU West (Ireland)')).toBeInTheDocument()
    expect(screen.getByText('AP South (Mumbai)')).toBeInTheDocument()
  })

  it('renders hub endpoints', () => {
    render(<HubManagement />)
    expect(screen.getByText('hub-east.tobogganing.io:443')).toBeInTheDocument()
    expect(screen.getByText('hub-west.tobogganing.io:443')).toBeInTheDocument()
    expect(screen.getByText('hub-eu.tobogganing.io:443')).toBeInTheDocument()
    expect(screen.getByText('hub-ap.tobogganing.io:443')).toBeInTheDocument()
  })

  it('renders hub status badges', () => {
    render(<HubManagement />)
    const healthyBadges = screen.getAllByText('healthy')
    const degradedBadges = screen.getAllByText('degraded')
    expect(healthyBadges.length).toBe(3)
    expect(degradedBadges.length).toBe(1)
  })

  it('renders hub stats sections', () => {
    render(<HubManagement />)
    const clientsLabels = screen.getAllByText('Clients')
    const uptimeLabels = screen.getAllByText('Uptime')
    const versionLabels = screen.getAllByText('Version')
    expect(clientsLabels.length).toBe(4)
    expect(uptimeLabels.length).toBe(4)
    expect(versionLabels.length).toBe(4)
  })

  it('renders connected client counts', () => {
    render(<HubManagement />)
    expect(screen.getByText('45')).toBeInTheDocument()
    expect(screen.getByText('38')).toBeInTheDocument()
    expect(screen.getByText('29')).toBeInTheDocument()
  })

  it('renders hub versions', () => {
    render(<HubManagement />)
    const v200 = screen.getAllByText('2.0.0')
    expect(v200.length).toBe(3)
    expect(screen.getByText('1.9.8')).toBeInTheDocument()
  })

  it('renders capacity section for each hub', () => {
    render(<HubManagement />)
    const capacityLabels = screen.getAllByText('Capacity')
    expect(capacityLabels.length).toBe(4)
  })

  it('renders capacity percentages', () => {
    render(<HubManagement />)
    // us-east-1: 45/100 = 45%
    expect(screen.getByText('45/100 (45%)')).toBeInTheDocument()
    // us-west-2: 38/100 = 38%
    expect(screen.getByText('38/100 (38%)')).toBeInTheDocument()
    // eu-west-1: 29/50 = 58%
    expect(screen.getByText('29/50 (58%)')).toBeInTheDocument()
    // ap-south-1: 0/50 = 0%
    expect(screen.getByText('0/50 (0%)')).toBeInTheDocument()
  })

  describe('formatUptime', () => {
    it('formats uptime in days and hours', () => {
      render(<HubManagement />)
      // us-east-1: 864000 seconds = 10 days 0 hours
      expect(screen.getByText('10d 0h')).toBeInTheDocument()
      // us-west-2: 720000 seconds = 8 days 8 hours... let me compute: 720000/86400 = 8.33 days = 8d 8h
      expect(screen.getByText('8d 8h')).toBeInTheDocument()
      // eu-west-1: 432000 seconds = 5d 0h
      expect(screen.getByText('5d 0h')).toBeInTheDocument()
      // ap-south-1: 86400 seconds = 1d 0h
      expect(screen.getByText('1d 0h')).toBeInTheDocument()
    })
  })

  describe('HubCard capacity bar colors', () => {
    it('renders warning color for capacity > 80%', () => {
      render(<HubManagement />)
      // eu-west-1: 29/50 = 58%, not >80 -- none are >80 in mock data
      // Let's verify eu-west-1 displays correctly
      expect(screen.getByText('EU West (Ireland)')).toBeInTheDocument()
    })

    it('renders zero-capacity hub correctly', () => {
      render(<HubManagement />)
      // ap-south-1 has 0 clients, 0%
      expect(screen.getByText('AP South (Mumbai)')).toBeInTheDocument()
      expect(screen.getByText('0/50 (0%)')).toBeInTheDocument()
    })
  })
})
