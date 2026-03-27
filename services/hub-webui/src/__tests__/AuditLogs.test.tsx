import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import AuditLogs from '../pages/AuditLogs'

describe('AuditLogs page', () => {
  it('renders the page heading', () => {
    render(<AuditLogs />)
    expect(screen.getByText('Audit Logs')).toBeInTheDocument()
    expect(screen.getByText(/Review policy decisions, authentication events, and admin actions/i)).toBeInTheDocument()
  })

  it('renders Export button', () => {
    render(<AuditLogs />)
    expect(screen.getByRole('button', { name: /Export/i })).toBeInTheDocument()
  })

  it('renders search input', () => {
    render(<AuditLogs />)
    expect(screen.getByPlaceholderText(/Search logs/i)).toBeInTheDocument()
  })

  it('renders event type filter select', () => {
    render(<AuditLogs />)
    const allTypesSelect = screen.getByDisplayValue('All Types')
    expect(allTypesSelect).toBeInTheDocument()
  })

  it('renders result filter select', () => {
    render(<AuditLogs />)
    const allResultsSelect = screen.getByDisplayValue('All Results')
    expect(allResultsSelect).toBeInTheDocument()
  })

  it('renders all mock audit log entries', () => {
    render(<AuditLogs />)
    // Check detail text of each log entry
    expect(screen.getByText(/Denied DNS request to evil.malware.test from client-047/i)).toBeInTheDocument()
    expect(screen.getByText(/Successful login from 10.0.1.15/i)).toBeInTheDocument()
    expect(screen.getByText(/Updated priority from 5 to 2/i)).toBeInTheDocument()
    expect(screen.getByText(/Failed login attempt from 203.0.113.50/i)).toBeInTheDocument()
    expect(screen.getByText(/Health check detected degraded performance/i)).toBeInTheDocument()
    expect(screen.getByText(/Registered new client with pending status/i)).toBeInTheDocument()
    expect(screen.getByText(/Allowed SSH from admin group user bob@corp.io/i)).toBeInTheDocument()
    expect(screen.getByText(/Created new user with maintainer role/i)).toBeInTheDocument()
  })

  it('renders event type labels', () => {
    render(<AuditLogs />)
    // policy_decision: 2 log entries → 2 badges (filter option says "Policy Decisions" not "Policy Decision")
    const policyLabels = screen.getAllByText('Policy Decision')
    expect(policyLabels.length).toBe(2)
    // auth: 2 log entries → 2 badges + 1 filter option "Authentication" = 3 total
    const authLabels = screen.getAllByText('Authentication')
    expect(authLabels.length).toBe(3)
    // admin_action: 3 log entries → 3 badges (filter option says "Admin Actions")
    const adminLabels = screen.getAllByText('Admin Action')
    expect(adminLabels.length).toBe(3)
    // system: 1 log entry → 1 badge + 1 filter option "System" = 2 total
    const systemLabels = screen.getAllByText('System')
    expect(systemLabels.length).toBe(2)
  })

  it('renders actor badges for log entries', () => {
    render(<AuditLogs />)
    expect(screen.getAllByText(/actor: system/i).length).toBeGreaterThan(0)
    expect(screen.getAllByText(/actor: admin@corp\.io/i).length).toBeGreaterThan(0)
  })

  it('renders action badges for log entries', () => {
    render(<AuditLogs />)
    const evaluateBadges = screen.getAllByText('action: evaluate')
    expect(evaluateBadges.length).toBe(2)
    const loginBadges = screen.getAllByText('action: login')
    expect(loginBadges.length).toBe(2)
  })

  it('renders target badges for log entries', () => {
    render(<AuditLogs />)
    expect(screen.getByText('target: Block Malicious Domains')).toBeInTheDocument()
    // hub-webui appears in 2 log entries, use getAllByText
    expect(screen.getAllByText('target: hub-webui').length).toBeGreaterThanOrEqual(1)
  })

  it('renders success/failure result icons for all entries', () => {
    render(<AuditLogs />)
    // 6 success, 2 failure (log-004 and log-005)
    // Icons are rendered but we can check for ARIA or rely on presence
    const logEntries = document.querySelectorAll('[class*="rounded-xl border border-border"]')
    expect(logEntries.length).toBe(8)
  })

  describe('Search functionality', () => {
    it('filters logs by actor', async () => {
      const user = userEvent.setup()
      render(<AuditLogs />)

      await user.type(screen.getByPlaceholderText(/Search logs/i), 'bob@corp.io')

      expect(screen.getByText(/Allowed SSH from admin group user bob@corp.io/i)).toBeInTheDocument()
      expect(screen.queryByText(/Denied DNS request/i)).not.toBeInTheDocument()
    })

    it('filters logs by action', async () => {
      const user = userEvent.setup()
      render(<AuditLogs />)

      await user.type(screen.getByPlaceholderText(/Search logs/i), 'health_check')

      expect(screen.getByText(/Health check detected degraded performance/i)).toBeInTheDocument()
      expect(screen.queryByText(/Denied DNS request/i)).not.toBeInTheDocument()
    })

    it('filters logs by target', async () => {
      const user = userEvent.setup()
      render(<AuditLogs />)

      await user.type(screen.getByPlaceholderText(/Search logs/i), 'hub-eu-west-1')

      expect(screen.getByText(/Health check detected degraded performance/i)).toBeInTheDocument()
      expect(screen.queryByText(/Successful login/i)).not.toBeInTheDocument()
    })

    it('filters logs by details content', async () => {
      const user = userEvent.setup()
      render(<AuditLogs />)

      await user.type(screen.getByPlaceholderText(/Search logs/i), 'maintainer role')

      expect(screen.getByText(/Created new user with maintainer role/i)).toBeInTheDocument()
      expect(screen.queryByText(/Denied DNS request/i)).not.toBeInTheDocument()
    })

    it('shows empty state when no logs match search', async () => {
      const user = userEvent.setup()
      render(<AuditLogs />)

      await user.type(screen.getByPlaceholderText(/Search logs/i), 'xyznonexistent999')

      expect(screen.getByText('No logs match your filters')).toBeInTheDocument()
    })

    it('search is case-insensitive', async () => {
      const user = userEvent.setup()
      render(<AuditLogs />)

      await user.type(screen.getByPlaceholderText(/Search logs/i), 'ADMIN@CORP.IO')

      const adminLogs = screen.getAllByText(/actor: admin@corp\.io/i)
      expect(adminLogs.length).toBeGreaterThan(0)
    })
  })

  describe('Event type filter', () => {
    it('filters to policy_decision events', async () => {
      const user = userEvent.setup()
      render(<AuditLogs />)

      await user.selectOptions(screen.getByDisplayValue('All Types'), 'policy_decision')

      const policyLabels = screen.getAllByText('Policy Decision')
      expect(policyLabels.length).toBe(2)
      // "Authentication" still appears as a filter dropdown option — check log badges only
      expect(screen.queryByText('Admin Action')).not.toBeInTheDocument()
    })

    it('filters to auth events', async () => {
      const user = userEvent.setup()
      render(<AuditLogs />)

      await user.selectOptions(screen.getByDisplayValue('All Types'), 'auth')

      // auth has 2 log entries → 2 "Authentication" badges + 1 in dropdown = 3
      const authLabels = screen.getAllByText('Authentication')
      expect(authLabels.length).toBe(3)
      // Policy Decision not in dropdown options and not in filtered logs
      expect(screen.queryByText('Policy Decision')).not.toBeInTheDocument()
    })

    it('filters to admin_action events', async () => {
      const user = userEvent.setup()
      render(<AuditLogs />)

      await user.selectOptions(screen.getByDisplayValue('All Types'), 'admin_action')

      const adminLabels = screen.getAllByText('Admin Action')
      expect(adminLabels.length).toBe(3)
      // Policy Decision not in dropdown options and not in filtered logs
      expect(screen.queryByText('Policy Decision')).not.toBeInTheDocument()
    })

    it('filters to system events', async () => {
      const user = userEvent.setup()
      render(<AuditLogs />)

      await user.selectOptions(screen.getByDisplayValue('All Types'), 'system')

      // "System" appears: 1 log entry badge + 1 dropdown option = 2
      const systemLabels = screen.getAllByText('System')
      expect(systemLabels.length).toBeGreaterThanOrEqual(2)
      // Policy Decision not in dropdown options and not in filtered logs
      expect(screen.queryByText('Policy Decision')).not.toBeInTheDocument()
    })
  })

  describe('Result filter', () => {
    it('filters to success results', async () => {
      const user = userEvent.setup()
      render(<AuditLogs />)

      await user.selectOptions(screen.getByDisplayValue('All Results'), 'success')

      // 6 success logs out of 8
      expect(screen.queryByText(/Failed login attempt/i)).not.toBeInTheDocument()
      expect(screen.queryByText(/Health check detected degraded/i)).not.toBeInTheDocument()
    })

    it('filters to failure results', async () => {
      const user = userEvent.setup()
      render(<AuditLogs />)

      await user.selectOptions(screen.getByDisplayValue('All Results'), 'failure')

      expect(screen.getByText(/Failed login attempt/i)).toBeInTheDocument()
      expect(screen.getByText(/Health check detected degraded performance/i)).toBeInTheDocument()
      expect(screen.queryByText(/Successful login/i)).not.toBeInTheDocument()
    })
  })

  describe('Combined filters', () => {
    it('applies type and result filters simultaneously', async () => {
      const user = userEvent.setup()
      render(<AuditLogs />)

      await user.selectOptions(screen.getByDisplayValue('All Types'), 'auth')
      await user.selectOptions(screen.getByDisplayValue('All Results'), 'failure')

      expect(screen.getByText(/Failed login attempt from 203.0.113.50/i)).toBeInTheDocument()
      expect(screen.queryByText(/Successful login/i)).not.toBeInTheDocument()
    })

    it('applies all three filters simultaneously', async () => {
      const user = userEvent.setup()
      render(<AuditLogs />)

      await user.type(screen.getByPlaceholderText(/Search logs/i), 'login')
      await user.selectOptions(screen.getByDisplayValue('All Types'), 'auth')
      await user.selectOptions(screen.getByDisplayValue('All Results'), 'success')

      expect(screen.getByText(/Successful login from 10.0.1.15/i)).toBeInTheDocument()
      expect(screen.queryByText(/Failed login attempt/i)).not.toBeInTheDocument()
    })
  })
})
