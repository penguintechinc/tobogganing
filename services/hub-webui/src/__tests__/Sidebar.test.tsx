import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { BrowserRouter } from 'react-router-dom'
import Sidebar from '../components/Sidebar'

function renderSidebar(collapsed = false, onToggle = vi.fn()) {
  return render(
    <BrowserRouter>
      <Sidebar collapsed={collapsed} onToggle={onToggle} />
    </BrowserRouter>
  )
}

describe('Sidebar component', () => {
  it('renders the brand name when expanded', () => {
    renderSidebar(false)
    expect(screen.getByText('Tobogganing')).toBeInTheDocument()
  })

  it('hides brand name when collapsed', () => {
    renderSidebar(true)
    expect(screen.queryByText('Tobogganing')).not.toBeInTheDocument()
  })

  it('renders all navigation links', () => {
    renderSidebar(false)
    expect(screen.getByText('Dashboard')).toBeInTheDocument()
    expect(screen.getByText('Policies')).toBeInTheDocument()
    expect(screen.getByText('Clients')).toBeInTheDocument()
    expect(screen.getByText('Hubs')).toBeInTheDocument()
    expect(screen.getByText('Users')).toBeInTheDocument()
    expect(screen.getByText('Identity')).toBeInTheDocument()
    expect(screen.getByText('Settings')).toBeInTheDocument()
    expect(screen.getByText('Audit Logs')).toBeInTheDocument()
  })

  it('hides navigation labels when collapsed', () => {
    renderSidebar(true)
    expect(screen.queryByText('Dashboard')).not.toBeInTheDocument()
    expect(screen.queryByText('Policies')).not.toBeInTheDocument()
    expect(screen.queryByText('Clients')).not.toBeInTheDocument()
  })

  it('renders correct number of nav links', () => {
    renderSidebar(false)
    const links = screen.getAllByRole('link')
    expect(links).toHaveLength(8)
  })

  it('nav links have correct hrefs', () => {
    renderSidebar(false)
    expect(screen.getByText('Dashboard').closest('a')).toHaveAttribute('href', '/')
    expect(screen.getByText('Policies').closest('a')).toHaveAttribute('href', '/policies')
    expect(screen.getByText('Clients').closest('a')).toHaveAttribute('href', '/clients')
    expect(screen.getByText('Hubs').closest('a')).toHaveAttribute('href', '/hubs')
    expect(screen.getByText('Users').closest('a')).toHaveAttribute('href', '/users')
    expect(screen.getByText('Identity').closest('a')).toHaveAttribute('href', '/identity')
    expect(screen.getByText('Settings').closest('a')).toHaveAttribute('href', '/settings')
    expect(screen.getByText('Audit Logs').closest('a')).toHaveAttribute('href', '/audit')
  })

  it('renders collapse toggle button when expanded', () => {
    renderSidebar(false)
    const btn = screen.getByRole('button', { name: /Collapse sidebar/i })
    expect(btn).toBeInTheDocument()
  })

  it('renders expand toggle button when collapsed', () => {
    renderSidebar(true)
    const btn = screen.getByRole('button', { name: /Expand sidebar/i })
    expect(btn).toBeInTheDocument()
  })

  it('calls onToggle when toggle button clicked', async () => {
    const onToggle = vi.fn()
    const user = userEvent.setup()
    renderSidebar(false, onToggle)

    await user.click(screen.getByRole('button', { name: /Collapse sidebar/i }))

    expect(onToggle).toHaveBeenCalledOnce()
  })

  it('adds title attribute to nav links when collapsed (for tooltip)', () => {
    renderSidebar(true)
    const links = screen.getAllByRole('link')
    const linksWithTitle = links.filter(link => link.hasAttribute('title'))
    expect(linksWithTitle.length).toBe(8)
  })

  it('does not add title to nav links when expanded', () => {
    renderSidebar(false)
    const links = screen.getAllByRole('link')
    const linksWithTitle = links.filter(link => link.hasAttribute('title'))
    expect(linksWithTitle.length).toBe(0)
  })

  it('renders as aside element', () => {
    renderSidebar(false)
    const aside = screen.getByRole('complementary')
    expect(aside).toBeInTheDocument()
  })

  it('applies correct width class when collapsed', () => {
    renderSidebar(true)
    const aside = screen.getByRole('complementary')
    expect(aside.className).toContain('w-16')
  })

  it('applies correct width class when expanded', () => {
    renderSidebar(false)
    const aside = screen.getByRole('complementary')
    expect(aside.className).toContain('w-60')
  })
})
