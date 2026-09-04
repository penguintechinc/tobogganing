import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { DashboardPage } from './DashboardPage';
import { AuthProvider } from '../context/AuthContext';
import { cacheClaims, CSRF_COOKIE_NAME } from '../api/authStorage';

jest.mock('../hooks/useManifest');

const mockUseManifest = jest.requireMock('../hooks/useManifest').useManifest as jest.Mock;

const renderDashboard = () => {
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
          <DashboardPage />
        </AuthProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
};

describe('DashboardPage', () => {
  beforeEach(() => {
    sessionStorage.clear();
    // Simulate an authenticated session: a csrf_token cookie (server-set,
    // readable) plus the cached claims AuthProvider hydrates from - there is
    // no client-readable access token anymore (HttpOnly cookie).
    document.cookie = `${CSRF_COOKIE_NAME}=test-csrf; path=/`;
    cacheClaims({
      sub: '1234567890',
      email: 'test@example.com',
      role: 'viewer',
      tenant: 't1',
      iat: 1516239022,
      exp: 9999999999,
    });
    jest.clearAllMocks();
  });

  afterEach(() => {
    document.cookie = `${CSRF_COOKIE_NAME}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
  });

  it('renders welcome message', () => {
    mockUseManifest.mockReturnValue({
      data: null,
      isLoading: false,
      error: null,
    });
    renderDashboard();
    expect(screen.getByText(/welcome/i)).toBeInTheDocument();
  });

  it('displays loading state for modules', () => {
    mockUseManifest.mockReturnValue({
      data: null,
      isLoading: true,
      error: null,
    });
    renderDashboard();
    expect(screen.getByText(/loading modules/i)).toBeInTheDocument();
  });

  it('shows user email and role', () => {
    mockUseManifest.mockReturnValue({
      data: null,
      isLoading: false,
      error: null,
    });
    renderDashboard();
    expect(screen.getByText(/test@example/)).toBeInTheDocument();
    expect(screen.getByText(/role:/i)).toBeInTheDocument();
  });

  it('displays modules when loaded', async () => {
    mockUseManifest.mockReturnValue({
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
        ],
        role: 'viewer',
      },
      isLoading: false,
      error: null,
    });
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText(/modules/i)).toBeInTheDocument();
      expect(screen.getByText('Analytics')).toBeInTheDocument();
    });
  });

  it('shows module navigation items', async () => {
    mockUseManifest.mockReturnValue({
      data: {
        modules: [
          {
            name: 'Analytics',
            nav: [
              { label: 'Dashboard', path: '/m/analytics/dashboard', icon: 'bar-chart' },
              { label: 'Reports', path: '/m/analytics/reports', icon: 'file' },
              { label: 'Metrics', path: '/m/analytics/metrics', icon: 'zap' },
            ],
            flags: {},
          },
        ],
        role: 'viewer',
      },
      isLoading: false,
      error: null,
    });
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText('Dashboard')).toBeInTheDocument();
      expect(screen.getByText('Reports')).toBeInTheDocument();
      expect(screen.getByText('Metrics')).toBeInTheDocument();
    });
  });

  it('shows "more" indicator when module has many navigation items', async () => {
    mockUseManifest.mockReturnValue({
      data: {
        modules: [
          {
            name: 'Analytics',
            nav: [
              { label: 'Dashboard', path: '/m/analytics/dashboard', icon: 'bar-chart' },
              { label: 'Reports', path: '/m/analytics/reports', icon: 'file' },
              { label: 'Metrics', path: '/m/analytics/metrics', icon: 'zap' },
              { label: 'Trends', path: '/m/analytics/trends', icon: 'line-chart' },
              { label: 'Forecast', path: '/m/analytics/forecast', icon: 'trending-up' },
            ],
            flags: {},
          },
        ],
        role: 'viewer',
      },
      isLoading: false,
      error: null,
    });
    renderDashboard();
    await waitFor(() => {
      expect(screen.getByText(/\+2 more/)).toBeInTheDocument();
    });
  });
});
