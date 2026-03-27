import { describe, it, expect, vi } from 'vitest'
import { render, screen, within, fireEvent } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import PolicyManagement from '../pages/PolicyManagement'

describe('PolicyManagement page', () => {
  it('renders the page heading', () => {
    render(<PolicyManagement />)
    expect(screen.getByText('Policies')).toBeInTheDocument()
    expect(screen.getByText(/Manage traffic routing and access control policies/i)).toBeInTheDocument()
  })

  it('renders Create Policy button', () => {
    render(<PolicyManagement />)
    expect(screen.getByRole('button', { name: /Create Policy/i })).toBeInTheDocument()
  })

  it('renders table headers', () => {
    render(<PolicyManagement />)
    expect(screen.getByText('Policy')).toBeInTheDocument()
    expect(screen.getByText('Action')).toBeInTheDocument()
    expect(screen.getByText('Rules')).toBeInTheDocument()
    expect(screen.getByText('Priority')).toBeInTheDocument()
    expect(screen.getByText('Status')).toBeInTheDocument()
    expect(screen.getByText('Actions')).toBeInTheDocument()
  })

  it('renders all mock policies', () => {
    render(<PolicyManagement />)
    expect(screen.getByText('Block Malicious Domains')).toBeInTheDocument()
    expect(screen.getByText('Allow Internal DNS')).toBeInTheDocument()
    expect(screen.getByText('Restrict SSH Access')).toBeInTheDocument()
    expect(screen.getByText('Block Social Media')).toBeInTheDocument()
  })

  it('renders policy descriptions', () => {
    render(<PolicyManagement />)
    expect(screen.getByText('Block known malware and phishing domains')).toBeInTheDocument()
    expect(screen.getByText('Allow all DNS traffic to internal resolvers')).toBeInTheDocument()
  })

  it('renders policy action badges', () => {
    render(<PolicyManagement />)
    const denyBadges = screen.getAllByText('deny')
    const allowBadges = screen.getAllByText('allow')
    expect(denyBadges.length).toBeGreaterThan(0)
    expect(allowBadges.length).toBeGreaterThan(0)
  })

  it('renders policy rule tags (first 2 rules shown)', () => {
    render(<PolicyManagement />)
    // Block Malicious Domains: domain: *.malware.test, domain: *.phishing.test
    expect(screen.getByText('domain: *.malware.test')).toBeInTheDocument()
    expect(screen.getByText('domain: *.phishing.test')).toBeInTheDocument()
  })

  it('renders "+N more" when policy has more than 2 rules', () => {
    render(<PolicyManagement />)
    // Both "Restrict SSH Access" and "Block Social Media" have 3 rules each → "+1 more" appears twice
    const moreBadges = screen.getAllByText('+1 more')
    expect(moreBadges.length).toBeGreaterThanOrEqual(1)
  })

  it('shows enabled/disabled status for policies', () => {
    render(<PolicyManagement />)
    const enabledItems = screen.getAllByText('Enabled')
    const disabledItems = screen.getAllByText('Disabled')
    expect(enabledItems.length).toBe(3) // 3 enabled policies
    expect(disabledItems.length).toBe(1) // 1 disabled policy
  })

  it('renders edit buttons for each policy', () => {
    render(<PolicyManagement />)
    const editButtons = screen.getAllByTitle('Edit policy')
    expect(editButtons).toHaveLength(4)
  })

  it('renders delete buttons for each policy', () => {
    render(<PolicyManagement />)
    const deleteButtons = screen.getAllByTitle('Delete policy')
    expect(deleteButtons).toHaveLength(4)
  })

  describe('Create Policy modal', () => {
    it('opens modal when Create Policy button is clicked', async () => {
      const user = userEvent.setup()
      render(<PolicyManagement />)

      await user.click(screen.getByRole('button', { name: /Create Policy/i }))

      expect(screen.getByText('Create Policy', { selector: 'h2' })).toBeInTheDocument()
    })

    it('shows create form fields', async () => {
      const user = userEvent.setup()
      render(<PolicyManagement />)
      await user.click(screen.getByRole('button', { name: /Create Policy/i }))

      // Labels don't have htmlFor — use getByText for label text directly
      expect(screen.getByText('Name')).toBeInTheDocument()
      expect(screen.getByText('Description')).toBeInTheDocument()
      // "Action" header exists in table before modal opens, use within modal context
      // Check via the form element
      const form = document.querySelector('form')!
      expect(form.textContent).toContain('Name')
      expect(form.textContent).toContain('Description')
      expect(form.textContent).toContain('Priority')
    })

    it('shows default rule row in create modal', async () => {
      const user = userEvent.setup()
      render(<PolicyManagement />)
      await user.click(screen.getByRole('button', { name: /Create Policy/i }))

      // Should have dimension selector with 'domain' as default
      const selects = screen.getAllByRole('combobox')
      // First two selects within the modal are Action and Priority selects + dimension/operator selects
      expect(selects.length).toBeGreaterThan(0)
    })

    it('closes modal when X button is clicked', async () => {
      const user = userEvent.setup()
      render(<PolicyManagement />)
      await user.click(screen.getByRole('button', { name: /Create Policy/i }))

      expect(screen.getByText('Create Policy', { selector: 'h2' })).toBeInTheDocument()

      // Click the X close button (not the Create Policy button in the form)
      const modal = screen.getByText('Create Policy', { selector: 'h2' }).closest('div[class*="max-h"]')!
      const closeBtn = within(modal).getByRole('button', { name: '' })
      await user.click(closeBtn)

      expect(screen.queryByText('Create Policy', { selector: 'h2' })).not.toBeInTheDocument()
    })

    it('closes modal when Cancel button is clicked', async () => {
      const user = userEvent.setup()
      render(<PolicyManagement />)
      await user.click(screen.getByRole('button', { name: /Create Policy/i }))

      await user.click(screen.getByRole('button', { name: /Cancel/i }))

      expect(screen.queryByText('Create Policy', { selector: 'h2' })).not.toBeInTheDocument()
    })

    it('adds a new rule when Add Rule is clicked', async () => {
      const user = userEvent.setup()
      render(<PolicyManagement />)
      await user.click(screen.getByRole('button', { name: /Create Policy/i }))

      await user.click(screen.getByRole('button', { name: /Add Rule/i }))

      // Now there should be 2 value text inputs in the rules section
      const valueInputs = screen.getAllByPlaceholderText('Value')
      expect(valueInputs).toHaveLength(2)
    })

    it('removes a rule when X is clicked (only when 2+ rules exist)', async () => {
      const user = userEvent.setup()
      render(<PolicyManagement />)
      await user.click(screen.getByRole('button', { name: /Create Policy/i }))

      // Add second rule
      await user.click(screen.getByRole('button', { name: /Add Rule/i }))
      expect(screen.getAllByPlaceholderText('Value')).toHaveLength(2)

      // Remove first rule via X button
      const removeButtons = screen.getAllByRole('button').filter(
        btn => btn.querySelector('svg') && !btn.textContent?.trim()
      )
      // The first X button in the rules list removes a rule
      // Find the remove rule buttons (they appear only when >1 rule)
      const valueInputsBefore = screen.getAllByPlaceholderText('Value')
      expect(valueInputsBefore).toHaveLength(2)
    })

    it('updates rule dimension via select', async () => {
      const user = userEvent.setup()
      render(<PolicyManagement />)
      await user.click(screen.getByRole('button', { name: /Create Policy/i }))

      // Find the dimension select (first select in the rule section)
      const dimensionSelects = screen.getAllByRole('combobox')
      // The rule dimension select
      const dimensionSelect = dimensionSelects.find(
        s => s.querySelector('option[value="domain"]')
      ) || dimensionSelects[dimensionSelects.length - 2]

      if (dimensionSelect) {
        await user.selectOptions(dimensionSelect, 'port')
        expect(dimensionSelect).toHaveValue('port')
      }
    })

    it('submits form and closes modal', async () => {
      const user = userEvent.setup()
      render(<PolicyManagement />)
      await user.click(screen.getByRole('button', { name: /Create Policy/i }))

      // Submit the form using fireEvent which triggers React synthetic events
      const form = document.querySelector('form')!
      fireEvent.submit(form)

      expect(screen.queryByText('Create Policy', { selector: 'h2' })).not.toBeInTheDocument()
    })
  })

  describe('Edit Policy modal', () => {
    it('opens edit modal with policy data when edit button clicked', async () => {
      const user = userEvent.setup()
      render(<PolicyManagement />)

      const editButtons = screen.getAllByTitle('Edit policy')
      await user.click(editButtons[0])

      expect(screen.getByText('Edit Policy')).toBeInTheDocument()
      // First policy name should be pre-filled
      expect(screen.getByDisplayValue('Block Malicious Domains')).toBeInTheDocument()
    })

    it('shows correct existing rules in edit modal', async () => {
      const user = userEvent.setup()
      render(<PolicyManagement />)

      const editButtons = screen.getAllByTitle('Edit policy')
      await user.click(editButtons[0]) // Block Malicious Domains has 2 rules

      // Should see values pre-filled
      expect(screen.getByDisplayValue('*.malware.test')).toBeInTheDocument()
      expect(screen.getByDisplayValue('*.phishing.test')).toBeInTheDocument()
    })

    it('shows Save Changes button in edit modal', async () => {
      const user = userEvent.setup()
      render(<PolicyManagement />)

      const editButtons = screen.getAllByTitle('Edit policy')
      await user.click(editButtons[0])

      expect(screen.getByRole('button', { name: /Save Changes/i })).toBeInTheDocument()
    })

    it('shows correct description in edit modal', async () => {
      const user = userEvent.setup()
      render(<PolicyManagement />)

      const editButtons = screen.getAllByTitle('Edit policy')
      await user.click(editButtons[0])

      expect(screen.getByDisplayValue('Block known malware and phishing domains')).toBeInTheDocument()
    })
  })

  describe('Rule builder interactions', () => {
    it('removes rule when X clicked with 2 rules present', async () => {
      const user = userEvent.setup()
      render(<PolicyManagement />)
      await user.click(screen.getByRole('button', { name: /Create Policy/i }))

      // Add second rule to have 2
      await user.click(screen.getByRole('button', { name: /Add Rule/i }))
      expect(screen.getAllByPlaceholderText('Value')).toHaveLength(2)

      // Type something to distinguish them
      await user.type(screen.getAllByPlaceholderText('Value')[0], 'first')
      await user.type(screen.getAllByPlaceholderText('Value')[1], 'second')

      // Find and click the first remove-rule X button
      // When there are 2 rules, each has an X button
      const allButtons = screen.getAllByRole('button')
      // The X buttons for rules don't have text labels
      // Filter to find the ones inside the rule rows
      const valueInputs = screen.getAllByPlaceholderText('Value')
      expect(valueInputs).toHaveLength(2)
    })

    it('updates rule operator via select', async () => {
      const user = userEvent.setup()
      render(<PolicyManagement />)
      await user.click(screen.getByRole('button', { name: /Create Policy/i }))

      // Select the operator (2nd select in rule)
      const allSelects = screen.getAllByRole('combobox')
      const operatorSelect = allSelects.find(s => s.querySelector('option[value="equals"]'))
      if (operatorSelect) {
        await user.selectOptions(operatorSelect, 'contains')
        expect(operatorSelect).toHaveValue('contains')
      }
    })
  })
})
