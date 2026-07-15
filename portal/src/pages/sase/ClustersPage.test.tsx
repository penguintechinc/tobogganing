import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ClustersPage } from './ClustersPage';
import * as saseApi from '../../api/sase';

jest.mock('../../api/sase');
const mockListClusters = saseApi.listClusters as jest.Mock;

const renderPage = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <ClustersPage />
    </QueryClientProvider>
  );
};

describe('ClustersPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders loading state initially', () => {
    mockListClusters.mockImplementation(
      () => new Promise(() => {}) // Never resolves
    );
    renderPage();
    expect(screen.getByTestId('datatable')).toBeInTheDocument();
  });

  it('renders clusters table with data', async () => {
    const mockClusters = [
      {
        id: '1',
        name: 'prod-cluster-1',
        region: 'us-east-1',
        datacenter: 'dc-1',
        status: 'active',
        client_count: 5,
      },
      {
        id: '2',
        name: 'staging-cluster',
        region: 'us-west-2',
        datacenter: 'dc-2',
        status: 'active',
        client_count: 2,
      },
    ];
    mockListClusters.mockResolvedValue(mockClusters);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('prod-cluster-1')).toBeInTheDocument();
      expect(screen.getByText('staging-cluster')).toBeInTheDocument();
    });
  });

  it('renders empty state when no clusters', async () => {
    mockListClusters.mockResolvedValue([]);
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('No data available')).toBeInTheDocument();
    });
  });

  it('shows error state on fetch failure', async () => {
    const error = new Error('Failed to fetch');
    mockListClusters.mockRejectedValue(error);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Error loading data')).toBeInTheDocument();
      expect(screen.getByText('Failed to fetch')).toBeInTheDocument();
    });
  });

  it('shows cluster detail section when expanded', async () => {
    const user = userEvent.setup();
    const mockClusters = [
      {
        id: '1',
        name: 'prod-cluster',
        region: 'us-east-1',
        datacenter: 'dc-1',
        status: 'active',
        client_count: 5,
      },
    ];
    mockListClusters.mockResolvedValue(mockClusters);

    renderPage();

    const expandButton = await screen.findByText('prod-cluster');
    await user.click(expandButton);

    // Look for the close button which only appears in the detail section
    await waitFor(() => {
      expect(screen.getByLabelText('Close details')).toBeInTheDocument();
    });
  });

  it('renders status badge correctly', async () => {
    const mockClusters = [
      {
        id: '1',
        name: 'cluster-1',
        region: 'us-east-1',
        datacenter: 'dc-1',
        status: 'active',
        client_count: 3,
      },
    ];
    mockListClusters.mockResolvedValue(mockClusters);

    renderPage();

    await waitFor(() => {
      const statusBadge = screen.getByText('active');
      expect(statusBadge).toHaveClass('bg-green-900');
    });
  });

  it('renders page title', async () => {
    mockListClusters.mockResolvedValue([]);
    renderPage();
    expect(screen.getByText('Clusters')).toBeInTheDocument();
  });

  it('calls refetch on retry when error occurs', async () => {
    const error = new Error('Failed to fetch');
    mockListClusters.mockRejectedValue(error);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Error loading data')).toBeInTheDocument();
    });

    const retryButton = screen.getByText('Retry');
    await userEvent.click(retryButton);

    await waitFor(() => {
      expect(mockListClusters).toHaveBeenCalledTimes(2);
    });
  });

  it('hides cluster detail when close button clicked', async () => {
    const user = userEvent.setup();
    const mockClusters = [
      {
        id: '1',
        name: 'prod-cluster',
        region: 'us-east-1',
        datacenter: 'dc-1',
        status: 'active',
        client_count: 5,
      },
    ];
    mockListClusters.mockResolvedValue(mockClusters);

    renderPage();

    const expandButton = await screen.findByText('prod-cluster');
    await user.click(expandButton);

    await waitFor(() => {
      expect(screen.getByLabelText('Close details')).toBeInTheDocument();
    });

    const closeButton = screen.getByLabelText('Close details');
    await user.click(closeButton);

    await waitFor(() => {
      expect(screen.queryByLabelText('Close details')).not.toBeInTheDocument();
    });
  });

  it('displays cluster detail information in grid', async () => {
    const user = userEvent.setup();
    const mockClusters = [
      {
        id: 'cluster-123',
        name: 'prod-cluster',
        region: 'eu-west-1',
        datacenter: 'eu-dc-1',
        status: 'active',
        client_count: 10,
      },
    ];
    mockListClusters.mockResolvedValue(mockClusters);

    renderPage();

    const expandButton = await screen.findByText('prod-cluster');
    await user.click(expandButton);

    await waitFor(() => {
      expect(screen.getAllByText('cluster-123').length).toBeGreaterThan(0);
      expect(screen.getAllByText('eu-west-1').length).toBeGreaterThan(0);
      expect(screen.getAllByText('eu-dc-1').length).toBeGreaterThan(0);
      expect(screen.getAllByText('10').length).toBeGreaterThan(0);
    });
  });

  it('shows inactive status with yellow color', async () => {
    const mockClusters = [
      {
        id: '1',
        name: 'staging-cluster',
        region: 'us-west-2',
        datacenter: 'dc-2',
        status: 'inactive',
        client_count: 1,
      },
    ];
    mockListClusters.mockResolvedValue(mockClusters);

    renderPage();

    await waitFor(() => {
      const badges = screen.getAllByText('inactive');
      expect(badges.some((el) => el.classList.contains('bg-yellow-900'))).toBe(true);
    });
  });

  it('shows inactive cluster status in detail view with yellow text', async () => {
    const user = userEvent.setup();
    const mockClusters = [
      {
        id: '1',
        name: 'inactive-cluster',
        region: 'us-west-2',
        datacenter: 'dc-2',
        status: 'inactive',
        client_count: 1,
      },
    ];
    mockListClusters.mockResolvedValue(mockClusters);

    renderPage();

    const expandButton = await screen.findByText('inactive-cluster');
    await user.click(expandButton);

    await waitFor(() => {
      const statusEls = screen.getAllByText('inactive');
      expect(statusEls.some((el) => el.classList.contains('text-yellow-400'))).toBe(true);
    });
  });
});
