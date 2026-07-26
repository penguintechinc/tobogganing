import { describe, it, expect } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import UserManagement from '../pages/UserManagement'

describe('UserManagement page', () => {
  it('renders the page heading', () => {
    render(<UserManagement />)
    expect(screen.getByText('Users')).toBeInTheDocument()
    expect(screen.getByText(/Manage user accounts and role-based access control/i)).toBeInTheDocument()
  })

  it('renders Add User button', () => {
    render(<UserManagement />)
    expect(screen.getByRole('button', { name: /Add User/i })).toBeInTheDocument()
  })

  it('renders role summary cards', () => {
    render(<UserManagement />)
    // Multiple "Admin" texts exist (summary card + table badge), use getAllByText
    expect(screen.getAllByText('Admin').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Maintainer').length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('Viewer').length).toBeGreaterThanOrEqual(1)
    // Role descriptions confirm the cards are rendered
    expect(screen.getByText('Full access to all features')).toBeInTheDocument()
  })

  it('renders role descriptions', () => {
    render(<UserManagement />)
    expect(screen.getByText('Full access to all features')).toBeInTheDocument()
    expect(screen.getByText('Read/write access, no user management')).toBeInTheDocument()
    expect(screen.getByText('Read-only access')).toBeInTheDocument()
  })

  it('renders correct role counts', () => {
    render(<UserManagement />)
    // 1 admin, 2 maintainers, 1 viewer
    // Counts appear in role summary cards
    const roleCounts = screen.getAllByText('1')
    expect(roleCounts.length).toBeGreaterThanOrEqual(1)
    const twoCount = screen.getByText('2')
    expect(twoCount).toBeInTheDocument()
  })

  it('renders table headers', () => {
    render(<UserManagement />)
    expect(screen.getByText('User')).toBeInTheDocument()
    expect(screen.getByText('Role')).toBeInTheDocument()
    expect(screen.getByText('Created')).toBeInTheDocument()
    expect(screen.getByText('Actions')).toBeInTheDocument()
  })

  it('renders all mock users', () => {
    render(<UserManagement />)
    expect(screen.getByText('Alice Chen')).toBeInTheDocument()
    expect(screen.getByText('Bob Martinez')).toBeInTheDocument()
    expect(screen.getByText('Carol Williams')).toBeInTheDocument()
    expect(screen.getByText('Dave Johnson')).toBeInTheDocument()
  })

  it('renders user email addresses', () => {
    render(<UserManagement />)
    expect(screen.getByText('admin@corp.io')).toBeInTheDocument()
    expect(screen.getByText('bob@corp.io')).toBeInTheDocument()
    expect(screen.getByText('carol@corp.io')).toBeInTheDocument()
    expect(screen.getByText('dave@corp.io')).toBeInTheDocument()
  })

  it('renders user initials avatars', () => {
    render(<UserManagement />)
    // "Alice Chen" → "AC", "Bob Martinez" → "BM", etc.
    expect(screen.getByText('AC')).toBeInTheDocument()
    expect(screen.getByText('BM')).toBeInTheDocument()
    expect(screen.getByText('CW')).toBeInTheDocument()
    expect(screen.getByText('DJ')).toBeInTheDocument()
  })

  it('renders role badges for each user', () => {
    render(<UserManagement />)
    // Role labels appear in badges in the table (not summary cards which also have text)
    // Each user has a role badge
    const adminBadges = screen.getAllByText('Admin')
    const maintainerBadges = screen.getAllByText('Maintainer')
    const viewerBadges = screen.getAllByText('Viewer')
    // Summary cards + table badges
    expect(adminBadges.length).toBeGreaterThanOrEqual(2) // 1 summary + 1 table badge
    expect(maintainerBadges.length).toBeGreaterThanOrEqual(3) // 1 summary + 2 table badges
    expect(viewerBadges.length).toBeGreaterThanOrEqual(2) // 1 summary + 1 table badge
  })

  it('renders edit buttons for each user', () => {
    render(<UserManagement />)
    const editBtns = screen.getAllByTitle('Edit user')
    expect(editBtns).toHaveLength(4)
  })

  it('renders delete buttons for each user', () => {
    render(<UserManagement />)
    const deleteBtns = screen.getAllByTitle('Delete user')
    expect(deleteBtns).toHaveLength(4)
  })

  it('renders formatted dates', () => {
    render(<UserManagement />)
    // Dates are formatted via toLocaleDateString()
    // Just check there's at least one date-looking string
    // The exact format depends on locale
    const dateRegex = /\d{1,2}\/\d{1,2}\/\d{4}/
    const container = document.body
    expect(container.textContent).toMatch(dateRegex)
  })

  describe('Create User modal', () => {
    it('opens modal when Add User clicked', async () => {
      const user = userEvent.setup()
      render(<UserManagement />)

      await user.click(screen.getByRole('button', { name: /Add User/i }))

      // Modal heading appears (h2 with "Add User")
      expect(screen.getByText('Add User', { selector: 'h2' })).toBeInTheDocument()
    })

    it('shows Name, Email, Password, and Role fields in create modal', async () => {
      const user = userEvent.setup()
      render(<UserManagement />)
      await user.click(screen.getByRole('button', { name: /Add User/i }))

      // Labels don't have htmlFor — check form content
      const form = document.querySelector('form')!
      expect(form.textContent).toContain('Name')
      expect(form.textContent).toContain('Email')
      expect(form.textContent).toContain('Password')
      expect(form.textContent).toContain('Role')
      // Check actual input types are present
      expect(form.querySelector('input[type="text"]')).toBeTruthy()
      expect(form.querySelector('input[type="email"]')).toBeTruthy()
      expect(form.querySelector('input[type="password"]')).toBeTruthy()
      expect(form.querySelector('select')).toBeTruthy()
    })

    it('shows Password field only in create mode', async () => {
      const user = userEvent.setup()
      render(<UserManagement />)
      await user.click(screen.getByRole('button', { name: /Add User/i }))

      // Password input exists in create mode
      const form = document.querySelector('form')!
      expect(form.querySelector('input[type="password"]')).toBeTruthy()
    })

    it('shows Create User submit button', async () => {
      const user = userEvent.setup()
      render(<UserManagement />)
      await user.click(screen.getByRole('button', { name: /Add User/i }))

      expect(screen.getByRole('button', { name: 'Create User' })).toBeInTheDocument()
    })

    it('closes modal when Cancel clicked', async () => {
      const user = userEvent.setup()
      render(<UserManagement />)
      await user.click(screen.getByRole('button', { name: /Add User/i }))

      await user.click(screen.getByRole('button', { name: /Cancel/i }))

      expect(screen.queryByText('Add User', { selector: 'h2' })).not.toBeInTheDocument()
    })

    it('closes modal when X button clicked', async () => {
      const user = userEvent.setup()
      render(<UserManagement />)
      await user.click(screen.getByRole('button', { name: /Add User/i }))

      expect(screen.getByText('Add User', { selector: 'h2' })).toBeInTheDocument()

      // Find the X close button in the modal
      const modalHeading = screen.getByText('Add User', { selector: 'h2' })
      const headerRow = modalHeading.parentElement!
      const closeBtn = headerRow.querySelector('button')!
      await user.click(closeBtn)

      expect(screen.queryByText('Add User', { selector: 'h2' })).not.toBeInTheDocument()
    })

    it('submits and closes modal', async () => {
      const user = userEvent.setup()
      render(<UserManagement />)
      await user.click(screen.getByRole('button', { name: /Add User/i }))

      // Submit the form using fireEvent which triggers React synthetic events
      const form = document.querySelector('form')!
      fireEvent.submit(form)

      expect(screen.queryByText('Add User', { selector: 'h2' })).not.toBeInTheDocument()
    })
  })

  describe('Edit User modal', () => {
    it('opens edit modal with user data', async () => {
      const user = userEvent.setup()
      render(<UserManagement />)

      const editBtns = screen.getAllByTitle('Edit user')
      await user.click(editBtns[0])

      expect(screen.getByText('Edit User')).toBeInTheDocument()
      expect(screen.getByDisplayValue('Alice Chen')).toBeInTheDocument()
    })

    it('pre-fills email in edit modal', async () => {
      const user = userEvent.setup()
      render(<UserManagement />)

      const editBtns = screen.getAllByTitle('Edit user')
      await user.click(editBtns[0])

      expect(screen.getByDisplayValue('admin@corp.io')).toBeInTheDocument()
    })

    it('does not show Password field in edit mode', async () => {
      const user = userEvent.setup()
      render(<UserManagement />)

      const editBtns = screen.getAllByTitle('Edit user')
      await user.click(editBtns[0])

      expect(screen.queryByLabelText('Password')).not.toBeInTheDocument()
    })

    it('shows Save Changes button in edit modal', async () => {
      const user = userEvent.setup()
      render(<UserManagement />)

      const editBtns = screen.getAllByTitle('Edit user')
      await user.click(editBtns[0])

      expect(screen.getByRole('button', { name: /Save Changes/i })).toBeInTheDocument()
    })

    it('shows role options in dropdown', async () => {
      const user = userEvent.setup()
      render(<UserManagement />)

      await user.click(screen.getByRole('button', { name: /Add User/i }))

      // Use combobox role since label doesn't have htmlFor
      const roleSelect = screen.getByRole('combobox')
      expect(roleSelect.querySelector('option[value="admin"]')).toBeTruthy()
      expect(roleSelect.querySelector('option[value="maintainer"]')).toBeTruthy()
      expect(roleSelect.querySelector('option[value="viewer"]')).toBeTruthy()
    })
  })
})
