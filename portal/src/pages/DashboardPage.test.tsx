import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { DashboardPage } from './DashboardPage';
import { AuthProvider } from '../context/AuthContext';

jest.mock('../hooks/useManifest');

const mockUseManifest = jest.requireMock('../hooks/useManifest')
  .useManifest as jest.Mock;

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
    sessionStorage.setItem(
      'access_token',
      'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwiZW1haWwiOiJ0ZXN0QGV4YW1wbGUuY29tIiwicm9sZSI6InZpZXdlciIsInRlbmFudCI6InQxIiwiaWF0IjoxNTE2MjM5MDIyLCJleHAiOjk5OTk5OTk5OTl9.mock'
    );
    jest.clearAllMocks();
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
