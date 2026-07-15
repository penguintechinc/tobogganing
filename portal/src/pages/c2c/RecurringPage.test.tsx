import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RecurringPage } from './RecurringPage';
import * as c2cApi from '../../api/c2c';

jest.mock('../../api/c2c');
jest.mock('../../hooks/useRole', () => ({
  useRole: () => ({ canWrite: () => true }),
}));

describe('RecurringPage', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    jest.clearAllMocks();
  });

  it('renders the page title', async () => {
    (c2cApi.listRecurringJobs as jest.Mock).mockResolvedValue([]);

    render(
      <QueryClientProvider client={queryClient}>
        <RecurringPage />
      </QueryClientProvider>
    );

    expect(screen.getByText('C2C Recurring Jobs')).toBeInTheDocument();
    expect(
      screen.getByText('Scheduled matrix runs and node health checks')
    ).toBeInTheDocument();
  });

  it('loads and displays recurring jobs', async () => {
    const mockJobs = [
      {
        id: 'job-1',
        job_type: 'matrix_run' as const,
        interval_seconds: 300,
        enabled: true,
      },
    ];

    (c2cApi.listRecurringJobs as jest.Mock).mockResolvedValue(mockJobs);

    render(
      <QueryClientProvider client={queryClient}>
        <RecurringPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('matrix_run')).toBeInTheDocument();
    });
  });

  it('renders create button', async () => {
    (c2cApi.listRecurringJobs as jest.Mock).mockResolvedValue([]);

    render(
      <QueryClientProvider client={queryClient}>
        <RecurringPage />
      </QueryClientProvider>
    );

    expect(screen.getByText('Create Job')).toBeInTheDocument();
  });

  it('shows form with job type selector', async () => {
    (c2cApi.listRecurringJobs as jest.Mock).mockResolvedValue([]);

    render(
      <QueryClientProvider client={queryClient}>
        <RecurringPage />
      </QueryClientProvider>
    );

    const createButton = screen.getByText('Create Job');
    fireEvent.click(createButton);

    await waitFor(() => {
      const select = screen.getByRole('combobox');
      expect(select).toBeInTheDocument();
      expect((select as HTMLSelectElement).value).toBe('matrix_run');
    });
  });

  it('displays enabled/disabled status badges', async () => {
    const mockJobs = [
      {
        id: 'job-1',
        job_type: 'matrix_run' as const,
        interval_seconds: 300,
        enabled: true,
      },
      {
        id: 'job-2',
        job_type: 'node_health' as const,
        interval_seconds: 600,
        enabled: false,
      },
    ];

    (c2cApi.listRecurringJobs as jest.Mock).mockResolvedValue(mockJobs);

    render(
      <QueryClientProvider client={queryClient}>
        <RecurringPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      const enabledBadge = screen.getAllByText('Enabled');
      const disabledBadge = screen.getByText('Disabled');
      expect(enabledBadge.length).toBeGreaterThan(0);
      expect(disabledBadge).toBeInTheDocument();
    });
  });
});
