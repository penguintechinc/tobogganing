import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ScheduledTestsPage } from './ScheduledTestsPage';
import * as wpcOps from '../../api/wpcOps';

jest.mock('../../api/wpcOps');
jest.mock('../../hooks/useRole', () => ({
  useRole: () => ({ role: 'admin', canWrite: () => true }),
}));

const createQueryClient = () =>
  new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

const mockTests: wpcOps.ScheduledTest[] = [
  {
    id: 'job-1',
    device_id: 'dev-1',
    test_type: 'latency',
    target: 'https://example.com',
    interval_seconds: 300,
    enabled: true,
    next_run_at: '2026-07-15T11:00:00Z',
    last_run_at: '2026-07-15T10:00:00Z',
    created_at: '2026-07-15T00:00:00Z',
  },
];

describe('ScheduledTestsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (wpcOps.listScheduledTests as jest.Mock).mockResolvedValue(mockTests);
  });

  it('renders the page title', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ScheduledTestsPage />
      </QueryClientProvider>
    );

    expect(screen.getByText('Scheduled Tests')).toBeInTheDocument();
  });

  it('loads and displays scheduled tests', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ScheduledTestsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('dev-1')).toBeInTheDocument();
      expect(screen.getByText('latency')).toBeInTheDocument();
    });
  });

  it('shows Create Test button', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ScheduledTestsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Create Test')).toBeInTheDocument();
    });
  });

  it('displays enable/disable and delete actions', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ScheduledTestsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      const buttons = screen.getAllByText(/Disable|Delete/);
      expect(buttons.length).toBeGreaterThan(0);
    });
  });

  it('displays empty state when no tests', async () => {
    (wpcOps.listScheduledTests as jest.Mock).mockResolvedValue([]);
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ScheduledTestsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('No data available')).toBeInTheDocument();
    });
  });

  it('shows loading state', async () => {
    (wpcOps.listScheduledTests as jest.Mock).mockImplementation(() => new Promise(() => {}));
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ScheduledTestsPage />
      </QueryClientProvider>
    );

    expect(screen.getByTestId('datatable')).toBeInTheDocument();
  });
});
