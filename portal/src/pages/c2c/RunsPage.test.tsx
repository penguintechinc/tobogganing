import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RunsPage } from './RunsPage';
import * as c2cApi from '../../api/c2c';

jest.mock('../../api/c2c');
jest.mock('../../hooks/useRole', () => ({
  useRole: () => ({ canWrite: () => true }),
}));

describe('RunsPage', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    jest.clearAllMocks();
  });

  it('renders the page title', async () => {
    (c2cApi.listRuns as jest.Mock).mockResolvedValue([]);

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
    const mockRuns = [
      {
        id: 'run-1',
        status: 'completed',
        total_pairs: 10,
        created_at: '2026-07-15T00:00:00Z',
      },
    ];

    (c2cApi.listRuns as jest.Mock).mockResolvedValue(mockRuns);

    render(
      <QueryClientProvider client={queryClient}>
        <RunsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('run-1')).toBeInTheDocument();
    });
  });

  it('renders create button', async () => {
    (c2cApi.listRuns as jest.Mock).mockResolvedValue([]);

    render(
      <QueryClientProvider client={queryClient}>
        <RunsPage />
      </QueryClientProvider>
    );

    expect(screen.getByText('Create Run')).toBeInTheDocument();
  });

  it('toggles form visibility', async () => {
    (c2cApi.listRuns as jest.Mock).mockResolvedValue([]);

    render(
      <QueryClientProvider client={queryClient}>
        <RunsPage />
      </QueryClientProvider>
    );

    const createButton = screen.getByText('Create Run');
    fireEvent.click(createButton);

    await waitFor(() => {
      expect(
        screen.getByPlaceholderText('latency, throughput')
      ).toBeInTheDocument();
    });
  });

  it('shows matrix detail when expanded', async () => {
    const mockRuns = [
      {
        id: 'run-1',
        status: 'completed',
        total_pairs: 10,
        created_at: '2026-07-15T00:00:00Z',
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

    (c2cApi.listRuns as jest.Mock).mockResolvedValue(mockRuns);
    (c2cApi.getRunMatrix as jest.Mock).mockResolvedValue(mockMatrix);

    render(
      <QueryClientProvider client={queryClient}>
        <RunsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('run-1')).toBeInTheDocument();
    });

    const detailButton = screen.getByText('Show Matrix');
    fireEvent.click(detailButton);

    await waitFor(() => {
      expect(screen.getByText('Matrix Results for Run run-1')).toBeInTheDocument();
    });
  });
});
