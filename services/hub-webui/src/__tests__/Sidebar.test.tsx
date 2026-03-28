import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import Sidebar from '../components/Sidebar'

function renderSidebar(path = '/', mobileOpen?: boolean, onMobileClose = vi.fn()) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Sidebar mobileOpen={mobileOpen} onMobileClose={onMobileClose} />
    </MemoryRouter>
  )
}

describe('Sidebar component', () => {
  it('renders the brand name', () => {
    renderSidebar()
    expect(screen.getAllByText('Tobogganing').length).toBeGreaterThanOrEqual(1)
  })

  it('renders all primary navigation items', () => {
    renderSidebar()
    expect(screen.getAllByText('Dashboard').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Policies').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Clients').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Hubs').length).toBeGreaterThanOrEqual(1)
  })

  it('renders management navigation items', () => {
    renderSidebar()
    expect(screen.getAllByText('Users').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Identity').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Settings').length).toBeGreaterThanOrEqual(1)
  })

  it('renders observability navigation items', () => {
    renderSidebar()
    expect(screen.getAllByText('Audit Logs').length).toBeGreaterThanOrEqual(1)
  })

  it('renders Management section header', () => {
    renderSidebar()
    expect(screen.getAllByText('Management').length).toBeGreaterThanOrEqual(1)
  })

  it('renders Observability section header', () => {
    renderSidebar()
    expect(screen.getAllByText('Observability').length).toBeGreaterThanOrEqual(1)
  })

  it('accepts mobileOpen prop without error', () => {
    expect(() => renderSidebar('/', true)).not.toThrow()
  })

  it('accepts onMobileClose callback without error', () => {
    const onMobileClose = vi.fn()
    expect(() => renderSidebar('/', false, onMobileClose)).not.toThrow()
  })
})
