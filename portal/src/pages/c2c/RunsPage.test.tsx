import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RunsPage } from './RunsPage';
import * as c2cApi from '../../api/c2c';
import { useRole } from '../../hooks/useRole';

jest.mock('../../api/c2c');
jest.mock('../../hooks/useRole', () => ({ useRole: jest.fn() }));

const mockUseRole = useRole as jest.Mock;

describe('RunsPage', () => {
  let queryClient: QueryClient;

  const mockRuns = [
    {
      id: 'run-1',
      status: 'completed' as const,
      total_pairs: 10,
      created_at: '2026-07-15T00:00:00Z',
    },
    {
      id: 'run-2',
      status: 'in_progress' as const,
      total_pairs: 20,
      created_at: '2026-07-15T01:00:00Z',
    },
  ];

  const mockMatrix = {
    regions: ['us-west-2', 'us-east-1'],
    cells: [
      {
        source: 'us-west-2',
        destination: 'us-east-1',
        loss_pct: 0.5,
        latency: 50,
        test_type: 'latency',
      },
    ],
  };

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    jest.clearAllMocks();
    (c2cApi.listRuns as jest.Mock).mockResolvedValue(mockRuns);
    (c2cApi.getRunMatrix as jest.Mock).mockResolvedValue(mockMatrix);
    (c2cApi.createRun as jest.Mock).mockResolvedValue({ id: 'run-3', ...mockRuns[0] });
    mockUseRole.mockReturnValue({ canWrite: () => true });
  });

  it('renders the page title', async () => {

    render(
      <QueryClientProvider client={queryClient}>
        <RunsPage />
      </QueryClientProvider>
    );

    expect(screen.getByText('C2C Runs')).toBeInTheDocument();
    expect(
      screen.getByText('Cluster-to-cluster matrix runs and results')
    ).toBeInTheDocument();
  });

  it('loads and displays runs', async () => {

    render(
      <QueryClientProvider client={queryClient}>
        <RunsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('run-1')).toBeInTheDocument();
      expect(screen.getByText('run-2')).toBeInTheDocument();
    });
  });

  it('renders create button for admin', async () => {

    render(
      <QueryClientProvider client={queryClient}>
        <RunsPage />
      </QueryClientProvider>
    );

    expect(screen.getByText('Create Run')).toBeInTheDocument();
  });

  it('hides create button for viewers', async () => {
    mockUseRole.mockReturnValue({ canWrite: () => false });

    render(
      <QueryClientProvider client={queryClient}>
        <RunsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.queryByText('Create Run')).not.toBeInTheDocument();
    });
  });

  it('toggles form visibility', async () => {

    render(
      <QueryClientProvider client={queryClient}>
        <RunsPage />
      </QueryClientProvider>
    );

    const createButton = screen.getByText('Create Run');
    await userEvent.click(createButton);

    await waitFor(() => {
      expect(
        screen.getByPlaceholderText('latency, throughput')
      ).toBeInTheDocument();
    });

    const cancelButton = screen.getByText('Cancel');
    await userEvent.click(cancelButton);

    await waitFor(() => {
      expect(
        screen.queryByPlaceholderText('latency, throughput')
      ).not.toBeInTheDocument();
    });
  });

  it('submits create run form', async () => {

    render(
      <QueryClientProvider client={queryClient}>
        <RunsPage />
      </QueryClientProvider>
    );

    const createButton = screen.getByText('Create Run');
    await userEvent.click(createButton);

    const testTypesInput = screen.getByPlaceholderText('latency, throughput');
    const submitButton = screen.getByRole('button', { name: /Create/ });

    await userEvent.clear(testTypesInput);
    await userEvent.type(testTypesInput, 'latency');
    await userEvent.click(submitButton);

    await waitFor(() => {
      expect(c2cApi.createRun).toHaveBeenCalledWith({
        test_types: ['latency'],
      });
    });
  });

  it('shows matrix detail when expanded', async () => {

    render(
      <QueryClientProvider client={queryClient}>
        <RunsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('run-1')).toBeInTheDocument();
    });

    const detailButtons = screen.getAllByText('Show Matrix');
    await userEvent.click(detailButtons[0]!);

    await waitFor(() => {
      expect(screen.getByText('Matrix Results for Run run-1')).toBeInTheDocument();
    });
  });

  it('hides matrix detail when collapsed', async () => {

    render(
      <QueryClientProvider client={queryClient}>
        <RunsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('run-1')).toBeInTheDocument();
    });

    const detailButtons = screen.getAllByText('Show Matrix');
    await userEvent.click(detailButtons[0]!);

    await waitFor(() => {
      expect(screen.getByText('Matrix Results for Run run-1')).toBeInTheDocument();
    });

    const hideButton = screen.getByText('Hide Matrix');
    await userEvent.click(hideButton);

    await waitFor(() => {
      expect(screen.queryByText('Matrix Results for Run run-1')).not.toBeInTheDocument();
    });
  });

  it('displays run status badges', async () => {

    render(
      <QueryClientProvider client={queryClient}>
        <RunsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('completed')).toBeInTheDocument();
      expect(screen.getByText('in_progress')).toBeInTheDocument();
    });
  });

  it('shows empty state when no runs', async () => {

    (c2cApi.listRuns as jest.Mock).mockResolvedValue([]);

    render(
      <QueryClientProvider client={queryClient}>
        <RunsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('No data available')).toBeInTheDocument();
    });
  });
});
