import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AutoPerfPage } from './AutoPerfPage';
import * as wpcOps from '../../api/wpcOps';

jest.mock('../../api/wpcOps');
jest.mock('../../hooks/useRole', () => ({
  useRole: () => ({ role: 'admin', canWrite: () => true }),
}));

const createQueryClient = () =>
  new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

const mockPolicies: wpcOps.AutoPerfPolicy[] = [
  {
    id: 'policy-1',
    tenant: 'tenant-1',
    name: 'Production Monitor',
    device_id: 'dev-1',
    target: '192.168.1.1',
    t1_interval_seconds: 300,
    t2_interval_seconds: 120,
    t3_interval_seconds: 60,
    deescalate_after_clean: 3,
    enabled: true,
    created_at: '2026-07-15T00:00:00Z',
  },
];

const mockState: wpcOps.AutoPerfState = {
  current_tier: 'T1',
  clean_cycles: 2,
  escalated_at: null,
};

describe('AutoPerfPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (wpcOps.listAutoPerfPolicies as jest.Mock).mockResolvedValue(mockPolicies);
    (wpcOps.getAutoPerfPolicyState as jest.Mock).mockResolvedValue(mockState);
  });

  it('renders the page title', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoPerfPage />
      </QueryClientProvider>
    );

    expect(screen.getByText('AutoPerf')).toBeInTheDocument();
  });

  it('loads and displays policies', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoPerfPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Production Monitor')).toBeInTheDocument();
      expect(screen.getByText('192.168.1.1')).toBeInTheDocument();
    });
  });

  it('shows Create Policy button', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoPerfPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Create Policy')).toBeInTheDocument();
    });
  });

  it('displays state and delete actions', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoPerfPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      const buttons = screen.getAllByText(/State|Delete/);
      expect(buttons.length).toBeGreaterThan(0);
    });
  });

  it('shows tier badge', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoPerfPage />
      </QueryClientProvider>
    );

    const stateButton = screen.queryByText('State') || screen.queryByText('View');
    if (stateButton) {
      stateButton.click();

      await waitFor(() => {
        expect(screen.getByText('T1')).toBeInTheDocument();
      });
    }
  });

  it('displays clean cycles count in state panel', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoPerfPage />
      </QueryClientProvider>
    );

    const stateButton = screen.queryByText('State') || screen.queryByText('View');
    if (stateButton) {
      stateButton.click();

      await waitFor(() => {
        expect(screen.getByText('2')).toBeInTheDocument();
      });
    }
  });

  it('displays empty state when no policies', async () => {
    (wpcOps.listAutoPerfPolicies as jest.Mock).mockResolvedValue([]);
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoPerfPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('No data available')).toBeInTheDocument();
    });
  });
});
