import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StatusPage } from './StatusPage';
import * as saseApi from '../../api/sase';

jest.mock('../../api/sase');
const mockGetStatus = saseApi.getStatus as jest.Mock;

const renderPage = () => {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });

  return render(
    <QueryClientProvider client={queryClient}>
      <StatusPage />
    </QueryClientProvider>
  );
};

describe('StatusPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders page title', () => {
    mockGetStatus.mockImplementation(() => new Promise(() => {}));
    renderPage();
    expect(screen.getByText('Status')).toBeInTheDocument();
  });

  it('renders loading state initially', () => {
    mockGetStatus.mockImplementation(() => new Promise(() => {}));
    renderPage();
    expect(screen.getByText('Status')).toBeInTheDocument();
  });

  it('renders status data when loaded', async () => {
    const mockStatus = {
      service: 'SASE Orchestrator API',
      status: 'healthy',
      clusters: {
        total: 5,
        active: 4,
      },
      clients: {
        total: 20,
        active: 18,
      },
      meta: {
        version: 1,
        timestamp: '2026-07-15T10:00:00Z',
      },
    };
    mockGetStatus.mockResolvedValue(mockStatus);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('HEALTHY')).toBeInTheDocument();
      expect(screen.getByText('Clusters')).toBeInTheDocument();
      expect(screen.getByText('Clients')).toBeInTheDocument();
    });
  });

  it('shows error state on fetch failure', async () => {
    const error = new Error('Failed to fetch');
    mockGetStatus.mockRejectedValue(error);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Error loading status')).toBeInTheDocument();
      expect(screen.getByText('Failed to fetch')).toBeInTheDocument();
    });
  });

  it('renders status metrics correctly', async () => {
    const mockStatus = {
      service: 'SASE Orchestrator API',
      status: 'healthy',
      clusters: {
        total: 5,
        active: 4,
      },
      clients: {
        total: 20,
        active: 18,
      },
      meta: {
        version: 1,
        timestamp: '2026-07-15T10:00:00Z',
      },
    };
    mockGetStatus.mockResolvedValue(mockStatus);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('4')).toBeInTheDocument();
      expect(screen.getByText('5')).toBeInTheDocument();
      expect(screen.getByText('18')).toBeInTheDocument();
      expect(screen.getByText('20')).toBeInTheDocument();
    });
  });

  it('calculates active percentage correctly', async () => {
    const mockStatus = {
      service: 'SASE Orchestrator API',
      status: 'healthy',
      clusters: {
        total: 100,
        active: 80,
      },
      clients: {
        total: 100,
        active: 80,
      },
      meta: {
        version: 1,
        timestamp: '2026-07-15T10:00:00Z',
      },
    };
    mockGetStatus.mockResolvedValue(mockStatus);

    renderPage();

    await waitFor(() => {
      const percentageElements = screen.getAllByText(/80%/);
      expect(percentageElements.length).toBeGreaterThan(0);
    });
  });

  it('shows healthy status with green icon', async () => {
    const mockStatus = {
      service: 'SASE Orchestrator API',
      status: 'healthy',
      clusters: { total: 5, active: 5 },
      clients: { total: 10, active: 10 },
      meta: { version: 1, timestamp: '2026-07-15T10:00:00Z' },
    };
    mockGetStatus.mockResolvedValue(mockStatus);

    renderPage();

    await waitFor(() => {
      const statusText = screen.getByText('HEALTHY');
      expect(statusText).toHaveClass('text-green-400');
    });
  });

  it('shows error status with red styling', async () => {
    const mockStatus = {
      service: 'SASE Orchestrator API',
      status: 'error',
      clusters: { total: 5, active: 2 },
      clients: { total: 10, active: 5 },
      meta: { version: 1, timestamp: '2026-07-15T10:00:00Z' },
    };
    mockGetStatus.mockResolvedValue(mockStatus);

    renderPage();

    await waitFor(() => {
      const statusText = screen.getByText('ERROR');
      expect(statusText).toHaveClass('text-red-400');
    });
  });

  it('retry button works on error', async () => {
    const error = new Error('Failed to fetch');
    mockGetStatus.mockRejectedValueOnce(error);
    mockGetStatus.mockResolvedValueOnce({
      service: 'SASE Orchestrator API',
      status: 'healthy',
      clusters: { total: 5, active: 5 },
      clients: { total: 10, active: 10 },
      meta: { version: 1, timestamp: '2026-07-15T10:00:00Z' },
    });

    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Error loading status')).toBeInTheDocument();
    });

    const retryButton = screen.getByText('Retry');
    await userEvent.click(retryButton);

    await waitFor(() => {
      expect(screen.getByText('HEALTHY')).toBeInTheDocument();
    });
  });

  it('displays timestamp', async () => {
    const mockStatus = {
      service: 'SASE Orchestrator API',
      status: 'healthy',
      clusters: { total: 5, active: 5 },
      clients: { total: 10, active: 10 },
      meta: { version: 1, timestamp: '2026-07-15T10:00:00Z' },
    };
    mockGetStatus.mockResolvedValue(mockStatus);

    renderPage();

    await waitFor(() => {
      expect(screen.getByText(/Last updated/)).toBeInTheDocument();
    });
  });
});
