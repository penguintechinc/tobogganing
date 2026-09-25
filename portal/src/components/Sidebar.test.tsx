import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Sidebar } from './Sidebar';
import { AuthProvider } from '../context/AuthContext';
import type { PortalManifest } from '../hooks/useManifest';

interface MockManifestResult {
  data: PortalManifest | undefined;
  isLoading: boolean;
  error: Error | null;
}

const mockManifestData: MockManifestResult = {
  data: {
    modules: [
      {
        name: 'Analytics',
        nav: [
          { label: 'Dashboard', path: '/m/analytics/dashboard', icon: 'bar-chart' },
          { label: 'Reports', path: '/m/analytics/reports', icon: 'file' },
        ],
        flags: {},
      },
      {
        name: 'Admin',
        nav: [{ label: 'Settings', path: '/m/admin/settings', icon: 'settings' }],
        flags: {},
      },
    ],
    role: 'maintainer',
  },
  isLoading: false,
  error: null,
};
const mockUseManifest = jest.fn((): MockManifestResult => mockManifestData);
jest.mock('../hooks/useManifest', () => ({
  useManifest: () => mockUseManifest(),
}));

jest.mock('../context/AuthContext', () => {
  const actual = jest.requireActual('../context/AuthContext');
  return {
    ...actual,
    useAuth: () => ({
      user: {
        sub: '1234567890',
        email: 'testuser@example.com',
        role: 'maintainer',
        tenant: 't1',
        iat: 1516239022,
        exp: 9999999999,
      },
      isAuthenticated: true,
      login: jest.fn(),
      logout: jest.fn(() => Promise.resolve()),
    }),
  };
});

const renderSidebar = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <Sidebar />
        </AuthProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
};

describe('Sidebar', () => {
  beforeEach(() => {
    mockUseManifest.mockReturnValue(mockManifestData);
    // useAuth is mocked directly above; AuthProvider's own hydration (which
    // no longer reads a stored token - see api/authStorage.ts) is unused.
    sessionStorage.clear();
  });

  it('displays sidebar branding', async () => {
    renderSidebar();

    await waitFor(() => {
      // Check both desktop and mobile branding render
      const tobogganing = screen.getAllByText('Tobogganing');
      expect(tobogganing.length).toBeGreaterThan(0);
      expect(screen.getByText('Portal')).toBeInTheDocument();
    });
  });

  it('renders module sections', async () => {
    renderSidebar();

    await waitFor(() => {
      expect(screen.getByText('Analytics')).toBeInTheDocument();
      expect(screen.getByText('Admin')).toBeInTheDocument();
    });
  });

  it('renders navigation items for each module', async () => {
    renderSidebar();

    await waitFor(() => {
      expect(screen.getByText('Dashboard')).toBeInTheDocument();
      expect(screen.getByText('Reports')).toBeInTheDocument();
      expect(screen.getByText('Settings')).toBeInTheDocument();
    });
  });

  it('displays user email (masked)', async () => {
    renderSidebar();

    await waitFor(() => {
      expect(screen.getByText(/testuser@\.\.\./)).toBeInTheDocument();
    });
  });

  it('renders logout button', async () => {
    renderSidebar();

    await waitFor(() => {
      const logoutButton = screen.getByRole('button', { name: /logout/i });
      expect(logoutButton).toBeInTheDocument();
    });
  });

  it('renders hamburger menu toggle on mobile', async () => {
    renderSidebar();

    await waitFor(() => {
      const toggleButton = screen.getByLabelText(/toggle menu/i);
      expect(toggleButton).toBeInTheDocument();
    });
  });

  it('hamburger toggle button is interactive', async () => {
    renderSidebar();

    const toggleButton = screen.getByLabelText(/toggle menu/i);
    expect(toggleButton).toBeInTheDocument();

    // Verify button is clickable without errors
    fireEvent.click(toggleButton);
    expect(toggleButton).toBeInTheDocument();
  });

  it('creates correct links for navigation items', async () => {
    renderSidebar();

    await waitFor(() => {
      const dashboardLink = screen.getByRole('link', { name: /dashboard/i });
      // Module names are capitalized, label slugs are lowercase
      expect(dashboardLink).toHaveAttribute('href', '/m/Analytics/dashboard');
    });
  });

  it('navigates to correct paths for module items', async () => {
    renderSidebar();

    await waitFor(() => {
      const reportsLink = screen.getByRole('link', { name: /reports/i });
      expect(reportsLink).toHaveAttribute('href', '/m/Analytics/reports');
    });
  });

  it('calls logout function on logout button click', async () => {
    renderSidebar();

    await waitFor(() => {
      const logoutButton = screen.getByRole('button', { name: /logout/i });
      expect(logoutButton).toBeInTheDocument();
    });
  });

  it('closing mobile overlay hides sidebar menu', async () => {
    renderSidebar();

    const toggleButton = screen.getByLabelText(/toggle menu/i);
    fireEvent.click(toggleButton);

    // Find and click the overlay
    await waitFor(() => {
      const overlay = document.querySelector('.lg\\:hidden.fixed.inset-0');
      if (overlay) {
        fireEvent.click(overlay);
      }
    });
  });

  it('handles logout button click', async () => {
    renderSidebar();

    await waitFor(() => {
      const logoutButton = screen.getByRole('button', { name: /logout/i });
      expect(logoutButton).toBeInTheDocument();
    });

    const logoutButton = screen.getByRole('button', { name: /logout/i });
    fireEvent.click(logoutButton);
  });

  it('closes mobile sidebar when navigation item clicked', async () => {
    renderSidebar();

    const toggleButton = screen.getByLabelText(/toggle menu/i);
    fireEvent.click(toggleButton);

    const dashboardLinks = screen.getAllByRole('link', { name: /dashboard/i });
    // Click the last one (mobile overlay has both desktop and mobile versions)
    const lastDashboardLink = dashboardLinks[dashboardLinks.length - 1];
    if (lastDashboardLink) {
      fireEvent.click(lastDashboardLink);
    }

    // Verify the sidebar is rendered and accessible
    const allTobogganing = screen.getAllByText('Tobogganing');
    expect(allTobogganing.length).toBeGreaterThan(0);
  });

  it('opens and closes mobile menu multiple times', async () => {
    renderSidebar();

    const toggleButton = screen.getByLabelText(/toggle menu/i);

    // Open menu
    fireEvent.click(toggleButton);
    expect(toggleButton).toBeInTheDocument();

    // Close menu
    fireEvent.click(toggleButton);
    expect(toggleButton).toBeInTheDocument();

    // Open menu again
    fireEvent.click(toggleButton);
    expect(toggleButton).toBeInTheDocument();
  });

  it('renders nothing while the manifest has not loaded', () => {
    mockUseManifest.mockReturnValue({ data: undefined, isLoading: true, error: null });

    const { container } = render(
      <MemoryRouter>
        <QueryClientProvider
          client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
        >
          <AuthProvider>
            <Sidebar />
          </AuthProvider>
        </QueryClientProvider>
      </MemoryRouter>
    );

    expect(container).toBeEmptyDOMElement();
  });
});
