import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AnalyticsPage } from './AnalyticsPage';
import * as netsvcsApi from '../../api/netsvcs';

jest.mock('../../api/netsvcs');
jest.mock('../../components/TrendsChart', () => ({
  __esModule: true,
  default: ({ data }: { data: Array<{ timestamp: string; value: number }> }) => (
    <div data-testid="trends-chart">Chart with {data.length} points</div>
  ),
}));
const mockedApi = netsvcsApi as jest.Mocked<typeof netsvcsApi>;

const meta = { version: 1, timestamp: '2026-08-20T10:00:00Z' };

describe('AnalyticsPage', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    jest.clearAllMocks();

    mockedApi.getAnalyticsSummary.mockResolvedValue([
      { key: 'zones', value: 3 },
      { key: 'records', value: 12 },
      { key: 'servers', value: 2 },
      { key: 'queries_24h', value: 5000 },
    ]);
    mockedApi.getAnalyticsQueries.mockResolvedValue({
      total_queries: 5000,
      total_cache_hits: 4000,
      total_errors: 10,
      cache_hit_rate: 80,
      timeline: [{ timestamp: '2026-08-20T09:00:00Z', queries: 100 }],
      meta,
    });
    mockedApi.getAnalyticsPerformance.mockResolvedValue([
      { metric: 'avg_response_ms', value: 12.5 },
      { metric: 'p95_response_ms', value: 25.1 },
    ]);
    mockedApi.getAnalyticsServers.mockResolvedValue([
      {
        server_id: 'srv-1',
        server_name: 'resolver-1',
        queries: 1000,
        cache_hits: 800,
        errors: 5,
        avg_response_ms: 12.5,
      },
    ]);
  });

  const renderPage = () =>
    render(
      <QueryClientProvider client={queryClient}>
        <AnalyticsPage />
      </QueryClientProvider>
    );

  it('renders the page title', async () => {
    renderPage();
    expect(screen.getByText('Analytics')).toBeInTheDocument();
  });

  it('renders summary cards from summary metrics', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Zones')).toBeInTheDocument();
      expect(screen.getByText('3')).toBeInTheDocument();
      expect(screen.getAllByText('5000').length).toBeGreaterThan(0);
    });
  });

  it('renders query volume totals', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('80.0%')).toBeInTheDocument();
    });
  });

  it('renders performance metric cards', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('avg_response_ms')).toBeInTheDocument();
      expect(screen.getAllByText('12.50').length).toBeGreaterThan(0);
    });
  });

  it('renders per-server breakdown table', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('resolver-1')).toBeInTheDocument();
    });
  });

  it('shows error state when query analytics fail and retries', async () => {
    mockedApi.getAnalyticsQueries.mockRejectedValue(new Error('Failed to fetch'));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Error loading query analytics')).toBeInTheDocument();
    });

    mockedApi.getAnalyticsQueries.mockResolvedValue({
      total_queries: 1,
      total_cache_hits: 1,
      total_errors: 0,
      cache_hit_rate: 100,
      timeline: [],
      meta,
    });
    fireEvent.click(screen.getByRole('button', { name: /retry/i }));

    await waitFor(() => {
      expect(mockedApi.getAnalyticsQueries).toHaveBeenCalledTimes(2);
    });
  });

  it('shows datatable error state when server analytics fail and retries', async () => {
    mockedApi.getAnalyticsServers.mockRejectedValue(new Error('Failed to fetch'));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Error loading data')).toBeInTheDocument();
    });

    mockedApi.getAnalyticsServers.mockResolvedValue([]);
    fireEvent.click(screen.getByText('Retry'));

    await waitFor(() => {
      expect(mockedApi.getAnalyticsServers).toHaveBeenCalledTimes(2);
    });
  });
});
