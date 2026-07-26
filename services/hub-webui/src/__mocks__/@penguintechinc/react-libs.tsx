import React from 'react'

// Mock types
export interface MenuCategory {
  header?: string
  items: { name: string; href: string; icon?: React.ComponentType<{ className?: string }> }[]
}

export interface AppConsoleVersionProps {
  appName?: string
  webuiVersion?: string
  styleConfig?: object
}

export interface LoginPageBuilderProps {
  branding?: { appName?: string; tagline?: string }
  onSuccess?: (result: {
    token?: string
    user?: { id: string; email: string; name?: string; roles?: string[] }
  }) => void
  children?: React.ReactNode
}

export interface SidebarMenuProps {
  logo?: React.ReactNode
  categories?: MenuCategory[]
  currentPath?: string
  onNavigate?: (href: string) => void
  mobileOpen?: boolean
  onMobileClose?: () => void
  closeOnNavigate?: boolean
  children?: React.ReactNode
}

export interface FormModalBuilderProps {
  children?: React.ReactNode
}

// Mock components
export const AppConsoleVersion = (_props: AppConsoleVersionProps) => null

export const LoginPageBuilder = ({ branding, onSuccess, children }: LoginPageBuilderProps) => (
  <div data-testid="login-page-builder">
    {branding?.appName && <div data-testid="app-name">{branding.appName}</div>}
    {branding?.tagline && <div data-testid="tagline">{branding.tagline}</div>}
    {onSuccess && (
      <button
        data-testid="mock-success-btn"
        onClick={() =>
          onSuccess({
            token: 'test-token',
            user: { id: 'u1', email: 'admin@test.com', name: 'Admin', roles: ['admin'] },
          })
        }
      >
        Trigger Success
      </button>
    )}
    {children}
  </div>
)

export const SidebarMenu = ({ logo, categories, children }: SidebarMenuProps) => (
  <div data-testid="sidebar-menu">
    {logo && <div data-testid="sidebar-logo">{logo}</div>}
    {categories?.map((cat, i) => (
      <div key={i}>
        {cat.header && <div>{cat.header}</div>}
        {cat.items.map((item) => (
          <a key={item.href} href={item.href}>
            {item.name}
          </a>
        ))}
      </div>
    ))}
    {children}
  </div>
)

export const FormModalBuilder = ({ children }: FormModalBuilderProps) => (
  <div data-testid="form-modal-builder">{children}</div>
)
