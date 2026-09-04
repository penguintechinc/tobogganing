import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ClientsPage } from './ClientsPage';
import * as saseApi from '../../api/sase';

jest.mock('../../api/sase');
const mockListClients = saseApi.listClients as jest.Mock;

const renderPage = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <ClientsPage />
    </QueryClientProvider>
  );
};

describe('ClientsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders loading state initially', () => {
    mockListClients.mockImplementation(
      () => new Promise(() => {}) // Never resolves
    );
    renderPage();
    expect(screen.getByTestId('datatable')).toBeInTheDocument();
  });

  it('renders clients table with data', async () => {
    const mockClients = [
      {
        id: '1',
        name: 'client-1',
        type: 'docker',
        cluster_id: 'cluster-1',
        status: 'active',
        last_seen: '2026-07-15T10:00:00Z',
      },
      {
        id: '2',
        name: 'client-2',
        type: 'native',
        cluster_id: 'cluster-1',
        status: 'active',
        last_seen: '2026-07-15T09:00:00Z',
      },
    ];
    mockListClients.mockResolvedValue(mockClients);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('client-1')).toBeInTheDocument();
      expect(screen.getByText('client-2')).toBeInTheDocument();
    });
  });

  it('renders empty state when no clients', async () => {
    mockListClients.mockResolvedValue([]);
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('No data available')).toBeInTheDocument();
    });
  });

  it('shows error state on fetch failure', async () => {
    const error = new Error('Failed to fetch');
    mockListClients.mockRejectedValue(error);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Error loading data')).toBeInTheDocument();
      expect(screen.getByText('Failed to fetch')).toBeInTheDocument();
    });
  });

  it('renders client type badges', async () => {
    const mockClients = [
      {
        id: '1',
        name: 'docker-client',
        type: 'docker',
        cluster_id: 'cluster-1',
        status: 'active',
        last_seen: '2026-07-15T10:00:00Z',
      },
      {
        id: '2',
        name: 'native-client',
        type: 'native',
        cluster_id: 'cluster-1',
        status: 'active',
        last_seen: '2026-07-15T09:00:00Z',
      },
    ];
    mockListClients.mockResolvedValue(mockClients);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('docker')).toBeInTheDocument();
      expect(screen.getByText('native')).toBeInTheDocument();
    });
  });

  it('renders page title', async () => {
    mockListClients.mockResolvedValue([]);
    renderPage();
    expect(screen.getByText('Clients')).toBeInTheDocument();
  });

  it('renders client status badge for active status', async () => {
    const mockClients = [
      {
        id: '1',
        name: 'client-1',
        type: 'docker',
        cluster_id: 'cluster-1',
        status: 'active',
        last_seen: '2026-07-15T10:00:00Z',
      },
    ];
    mockListClients.mockResolvedValue(mockClients);

    renderPage();

    await waitFor(() => {
      const statusBadge = screen.getByText('active');
      expect(statusBadge).toHaveClass('bg-green-900');
    });
  });

  it('renders client status badge for inactive status', async () => {
    const mockClients = [
      {
        id: '1',
        name: 'client-1',
        type: 'docker',
        cluster_id: 'cluster-1',
        status: 'inactive',
        last_seen: '2026-07-15T10:00:00Z',
      },
    ];
    mockListClients.mockResolvedValue(mockClients);

    renderPage();

    await waitFor(() => {
      const statusBadge = screen.getByText('inactive');
      expect(statusBadge).toHaveClass('bg-yellow-900');
    });
  });

  it('formats last_seen timestamp', async () => {
    const mockClients = [
      {
        id: '1',
        name: 'client-1',
        type: 'docker',
        cluster_id: 'cluster-1',
        status: 'active',
        last_seen: '2026-07-15T15:30:00Z',
      },
    ];
    mockListClients.mockResolvedValue(mockClients);

    renderPage();

    await waitFor(() => {
      // Check that date formatting is applied
      const dateElement = screen.getByText(/15.*2026/);
      expect(dateElement).toBeInTheDocument();
    });
  });

  it('calls refetch on retry when error occurs', async () => {
    const error = new Error('Failed to fetch');
    mockListClients.mockRejectedValue(error);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Error loading data')).toBeInTheDocument();
    });

    const retryButton = screen.getByText('Retry');
    await userEvent.click(retryButton);

    await waitFor(() => {
      expect(mockListClients).toHaveBeenCalledTimes(2);
    });
  });
});
