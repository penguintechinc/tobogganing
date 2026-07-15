import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RecurringPage } from './RecurringPage';
import * as c2cApi from '../../api/c2c';
import { useRole } from '../../hooks/useRole';

jest.mock('../../api/c2c');
jest.mock('../../hooks/useRole', () => ({ useRole: jest.fn() }));

const mockUseRole = useRole as jest.Mock;

describe('RecurringPage', () => {
  let queryClient: QueryClient;

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

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    jest.clearAllMocks();
    (c2cApi.listRecurringJobs as jest.Mock).mockResolvedValue(mockJobs);
    (c2cApi.createRecurringJob as jest.Mock).mockResolvedValue({ id: 'job-3', ...mockJobs[0] });
    (c2cApi.deleteRecurringJob as jest.Mock).mockResolvedValue(undefined);
    mockUseRole.mockReturnValue({ canWrite: () => true });
  });

  it('renders the page title', async () => {

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

    render(
      <QueryClientProvider client={queryClient}>
        <RecurringPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('matrix_run')).toBeInTheDocument();
      expect(screen.getByText('node_health')).toBeInTheDocument();
    });
  });

  it('renders create button for admin', async () => {

    render(
      <QueryClientProvider client={queryClient}>
        <RecurringPage />
      </QueryClientProvider>
    );

    expect(screen.getByText('Create Job')).toBeInTheDocument();
  });

  it('hides create button for viewers', async () => {
    mockUseRole.mockReturnValue({ canWrite: () => false });

    render(
      <QueryClientProvider client={queryClient}>
        <RecurringPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.queryByText('Create Job')).not.toBeInTheDocument();
    });
  });

  it('shows form with job type selector', async () => {

    render(
      <QueryClientProvider client={queryClient}>
        <RecurringPage />
      </QueryClientProvider>
    );

    const createButton = screen.getByText('Create Job');
    await userEvent.click(createButton);

    await waitFor(() => {
      const select = screen.getByRole('combobox');
      expect(select).toBeInTheDocument();
      expect((select as HTMLSelectElement).value).toBe('matrix_run');
    });
  });

  it('submits create job form with job_type selector', async () => {

    render(
      <QueryClientProvider client={queryClient}>
        <RecurringPage />
      </QueryClientProvider>
    );

    const createButton = screen.getByText('Create Job');
    await userEvent.click(createButton);

    const jobTypeSelect = screen.getByRole('combobox');
    const intervalInput = screen.getByDisplayValue('300') as HTMLInputElement;

    await userEvent.selectOptions(jobTypeSelect, 'node_health');
    await userEvent.clear(intervalInput);
    await userEvent.type(intervalInput, '1200');

    const submitButton = screen.getByRole('button', { name: /Create/ });
    await userEvent.click(submitButton);

    await waitFor(() => {
      expect(c2cApi.createRecurringJob).toHaveBeenCalledWith({
        endpoint_ids: null,
        job_type: 'node_health',
        interval_seconds: 1200,
      });
    });
  });

  it('toggles form visibility', async () => {

    render(
      <QueryClientProvider client={queryClient}>
        <RecurringPage />
      </QueryClientProvider>
    );

    const createButton = screen.getByText('Create Job');
    await userEvent.click(createButton);

    await waitFor(() => {
      expect(screen.getByRole('combobox')).toBeInTheDocument();
    });

    const cancelButton = screen.getByText('Cancel');
    await userEvent.click(cancelButton);

    await waitFor(() => {
      expect(screen.queryByRole('combobox')).not.toBeInTheDocument();
    });
  });

  it('displays enabled/disabled status badges', async () => {

    render(
      <QueryClientProvider client={queryClient}>
        <RecurringPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      const enabledBadges = screen.getAllByText('Enabled');
      const disabledBadge = screen.getByText('Disabled');
      expect(enabledBadges.length).toBeGreaterThan(0);
      expect(disabledBadge).toBeInTheDocument();
    });
  });

  it('deletes recurring job', async () => {

    render(
      <QueryClientProvider client={queryClient}>
        <RecurringPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('matrix_run')).toBeInTheDocument();
    });

    const deleteButtons = screen.getAllByText('Delete');
    await userEvent.click(deleteButtons[0]!);

    await waitFor(() => {
      expect(c2cApi.deleteRecurringJob).toHaveBeenCalledWith('job-1');
    });
  });

  it('shows empty state when no jobs', async () => {

    (c2cApi.listRecurringJobs as jest.Mock).mockResolvedValue([]);

    render(
      <QueryClientProvider client={queryClient}>
        <RecurringPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('No data available')).toBeInTheDocument();
    });
  });
});
