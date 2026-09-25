import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DnsServersPage } from './DnsServersPage';
import * as netsvcsApi from '../../api/netsvcs';

jest.mock('../../api/netsvcs');
jest.mock('../../components/LiveChart', () => ({
  __esModule: true,
  default: ({ data }: { data: Array<{ timestamp: string }> }) => (
    <div data-testid="live-chart">Chart with {data.length} points</div>
  ),
}));
const mockedApi = netsvcsApi as jest.Mocked<typeof netsvcsApi>;

const mockServers: netsvcsApi.DnsServer[] = [
  {
    id: 'srv-1',
    name: 'resolver-1',
    status: 'online',
    version: '1.2.0',
    region: 'us-east-1',
    hostname: 'resolver-1.internal',
    last_heartbeat: '2026-08-20T09:00:00Z',
    created_at: '2026-08-01T00:00:00Z',
  },
  {
    id: 'srv-2',
    name: 'resolver-2',
    status: 'offline',
    version: null,
    region: null,
    hostname: null,
    last_heartbeat: null,
    created_at: '2026-08-02T00:00:00Z',
  },
];

const mockMetrics: netsvcsApi.DnsServerMetric[] = [
  {
    server_id: 'srv-1',
    timestamp: '2026-08-20T09:00:00Z',
    queries_total: 1000,
    cache_hits: 800,
    errors: 2,
    avg_response_ms: 12.5,
  },
];

describe('DnsServersPage', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    jest.clearAllMocks();
    mockedApi.listDnsServers.mockResolvedValue(mockServers);
    mockedApi.getDnsServerMetrics.mockResolvedValue(mockMetrics);
    mockedApi.deleteDnsServer.mockResolvedValue({
      message: 'DNS server deleted successfully',
      meta: { version: 1, timestamp: '2026-08-20T09:00:00Z' },
    });
  });

  const renderPage = () =>
    render(
      <QueryClientProvider client={queryClient}>
        <DnsServersPage />
      </QueryClientProvider>
    );

  it('renders the page title', async () => {
    renderPage();
    expect(screen.getByText('DNS Servers')).toBeInTheDocument();
  });

  it('renders servers table with data', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('resolver-1')).toBeInTheDocument();
      expect(screen.getByText('resolver-2')).toBeInTheDocument();
    });
  });

  it('shows null fields as placeholders', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('never')).toBeInTheDocument();
    });
  });

  it('shows empty state when no servers', async () => {
    mockedApi.listDnsServers.mockResolvedValue([]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('No data available')).toBeInTheDocument();
    });
  });

  it('shows error state on fetch failure', async () => {
    mockedApi.listDnsServers.mockRejectedValue(new Error('Failed to fetch'));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Error loading data')).toBeInTheDocument();
    });
  });

  it('expands a server row to show the metrics panel', async () => {
    const user = userEvent.setup();
    renderPage();

    const expandButton = await screen.findByText('resolver-1');
    await user.click(expandButton);

    await waitFor(() => {
      expect(screen.getByText('Metrics: resolver-1')).toBeInTheDocument();
      expect(mockedApi.getDnsServerMetrics).toHaveBeenCalledWith('srv-1');
    });
  });

  it('closes the metrics panel', async () => {
    const user = userEvent.setup();
    renderPage();

    const expandButton = await screen.findByText('resolver-1');
    await user.click(expandButton);

    await waitFor(() => expect(screen.getByText('Metrics: resolver-1')).toBeInTheDocument());
    fireEvent.click(screen.getByLabelText('Close metrics'));

    await waitFor(() => {
      expect(screen.queryByText('Metrics: resolver-1')).not.toBeInTheDocument();
    });
  });

  it('deletes a server after confirmation', async () => {
    window.confirm = jest.fn(() => true);
    renderPage();

    await waitFor(() =>
      expect(screen.getAllByLabelText(/Delete server/).length).toBeGreaterThan(0)
    );
    fireEvent.click(screen.getAllByLabelText(/Delete server/)[0]!);

    await waitFor(() => {
      expect(mockedApi.deleteDnsServer).toHaveBeenCalledWith('srv-1');
    });
  });

  it('alerts when deleting a server fails', async () => {
    const alertSpy = jest.spyOn(window, 'alert').mockImplementation();
    window.confirm = jest.fn(() => true);
    mockedApi.deleteDnsServer.mockRejectedValue(new Error('boom'));
    renderPage();

    await waitFor(() =>
      expect(screen.getAllByLabelText(/Delete server/).length).toBeGreaterThan(0)
    );
    fireEvent.click(screen.getAllByLabelText(/Delete server/)[0]!);

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('Failed to delete DNS server');
    });
    alertSpy.mockRestore();
  });

  it('collapses the metrics panel when the expanded server is deleted', async () => {
    const user = userEvent.setup();
    window.confirm = jest.fn(() => true);
    renderPage();

    const expandButton = await screen.findByText('resolver-1');
    await user.click(expandButton);
    await waitFor(() => expect(screen.getByText('Metrics: resolver-1')).toBeInTheDocument());

    fireEvent.click(screen.getAllByLabelText(/Delete server/)[0]!);

    await waitFor(() => {
      expect(mockedApi.deleteDnsServer).toHaveBeenCalledWith('srv-1');
      expect(screen.queryByText('Metrics: resolver-1')).not.toBeInTheDocument();
    });
  });

  it('retries the servers query on error', async () => {
    mockedApi.listDnsServers.mockRejectedValue(new Error('Failed to fetch'));
    renderPage();

    await waitFor(() => expect(screen.getByText('Error loading data')).toBeInTheDocument());

    mockedApi.listDnsServers.mockResolvedValue(mockServers);
    fireEvent.click(screen.getByText('Retry'));

    await waitFor(() => {
      expect(mockedApi.listDnsServers).toHaveBeenCalledTimes(2);
    });
  });

  it('does not delete a server when confirmation is declined', async () => {
    window.confirm = jest.fn(() => false);
    renderPage();

    await waitFor(() =>
      expect(screen.getAllByLabelText(/Delete server/).length).toBeGreaterThan(0)
    );
    fireEvent.click(screen.getAllByLabelText(/Delete server/)[0]!);

    expect(mockedApi.deleteDnsServer).not.toHaveBeenCalled();
  });
});
