import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import IdentityProviders from '../pages/IdentityProviders'

describe('IdentityProviders page', () => {
  it('renders the page heading', () => {
    render(<IdentityProviders />)
    expect(screen.getByText('Identity Providers')).toBeInTheDocument()
    expect(screen.getByText(/Configure authentication sources and user provisioning/i)).toBeInTheDocument()
  })

  it('renders all provider cards', () => {
    render(<IdentityProviders />)
    expect(screen.getByText('Local Users')).toBeInTheDocument()
    expect(screen.getByText('Azure AD (OIDC)')).toBeInTheDocument()
    expect(screen.getByText('Okta (SAML)')).toBeInTheDocument()
    expect(screen.getByText('SCIM Provisioning')).toBeInTheDocument()
  })

  it('renders provider type labels', () => {
    render(<IdentityProviders />)
    expect(screen.getByText('Local')).toBeInTheDocument()
    expect(screen.getByText('OIDC')).toBeInTheDocument()
    expect(screen.getByText('SAML')).toBeInTheDocument()
    expect(screen.getByText('SCIM')).toBeInTheDocument()
  })

  it('renders provider descriptions', () => {
    render(<IdentityProviders />)
    expect(screen.getByText(/Built-in user management with email\/password/i)).toBeInTheDocument()
    expect(screen.getByText(/OpenID Connect for SSO/i)).toBeInTheDocument()
    expect(screen.getByText(/SAML 2\.0 for enterprise SSO/i)).toBeInTheDocument()
    expect(screen.getByText(/System for Cross-domain Identity Management/i)).toBeInTheDocument()
  })

  it('renders Premium badges for non-local providers', () => {
    render(<IdentityProviders />)
    const premiumBadges = screen.getAllByText('Premium')
    expect(premiumBadges.length).toBe(3) // OIDC, SAML, SCIM
  })

  it('does not render Premium badge for Local provider', () => {
    render(<IdentityProviders />)
    // Local Users is not premium - just verify "Local Users" card does not have Premium in its vicinity
    const localCard = screen.getByText('Local Users').closest('div')!
    expect(localCard.textContent).not.toContain('Premium')
  })

  it('renders configure buttons for each provider', () => {
    render(<IdentityProviders />)
    const configBtns = screen.getAllByRole('button', { name: /Configure/i })
    expect(configBtns.length).toBe(4)
  })

  it('disables Configure button for premium disabled providers', () => {
    render(<IdentityProviders />)
    const configBtns = screen.getAllByRole('button', { name: /Configure/i })
    // Premium providers that are disabled (OIDC, SAML, SCIM) should be disabled
    const disabledBtns = configBtns.filter(btn => btn.hasAttribute('disabled'))
    expect(disabledBtns.length).toBe(3)
  })

  it('enables Configure button for Local provider', () => {
    render(<IdentityProviders />)
    const configBtns = screen.getAllByRole('button', { name: /Configure/i })
    const enabledBtns = configBtns.filter(btn => !btn.hasAttribute('disabled'))
    expect(enabledBtns.length).toBe(1) // Only Local Users
  })

  it('renders toggle buttons for each provider', () => {
    render(<IdentityProviders />)
    // Each provider has a toggle button (enable/disable)
    const toggleBtns = screen.getAllByRole('button', { name: /Disable|Enable/i })
    expect(toggleBtns.length).toBe(4)
  })

  it('renders license info banner', () => {
    render(<IdentityProviders />)
    expect(screen.getByText('Premium Feature')).toBeInTheDocument()
    expect(screen.getByText(/OIDC, SAML, and SCIM integrations require a premium license/i)).toBeInTheDocument()
  })

  it('renders sales contact link', () => {
    render(<IdentityProviders />)
    const salesLink = screen.getByRole('link', { name: /sales@penguintech\.io/i })
    expect(salesLink).toBeInTheDocument()
    expect(salesLink).toHaveAttribute('href', 'mailto:sales@penguintech.io')
  })

  it('renders config summary for local provider', () => {
    render(<IdentityProviders />)
    // Local provider has: password_policy, mfa_enabled
    expect(screen.getByText('password policy')).toBeInTheDocument()
    expect(screen.getByText('mfa enabled')).toBeInTheDocument()
    expect(screen.getByText('strong')).toBeInTheDocument()
    expect(screen.getByText('false')).toBeInTheDocument()
  })

  it('masks token and secret config values', () => {
    render(<IdentityProviders />)
    // SCIM has bearer_token which should be masked
    const maskedValues = screen.getAllByText('********')
    expect(maskedValues.length).toBeGreaterThan(0)
  })

  it('renders non-sensitive OIDC config values', () => {
    render(<IdentityProviders />)
    // OIDC: issuer, client_id, redirect_uri — none contain "token" or "secret"
    expect(screen.getByText('https://login.microsoftonline.com/tenant-id')).toBeInTheDocument()
    expect(screen.getByText('app-client-id')).toBeInTheDocument()
  })

  it('renders enabled state for Local provider', () => {
    render(<IdentityProviders />)
    // Local provider has enabled: true, so toggle shows enabled
    // The enabled provider has a ToggleRight icon (not left)
    // Just verify Local Users card renders with enabled border
    const localCard = screen.getByText('Local Users').closest('[class*="rounded-xl"]')
    expect(localCard?.className).toContain('border-accent')
  })
})
