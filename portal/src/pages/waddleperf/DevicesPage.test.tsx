import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { DevicesPage } from './DevicesPage';
import * as waddleperf from '../../api/waddleperf';

jest.mock('../../api/waddleperf');

const mockWaddleperf = waddleperf as jest.Mocked<typeof waddleperf>;

describe('DevicesPage', () => {
  const mockDevices: waddleperf.Device[] = [
    {
      id: 'd1',
      name: 'Device 1',
      serial: 'SN001',
      hostname: 'host1.local',
      os: 'Linux',
      org_unit_id: 'ou-prod',
      status: 'online',
      last_heartbeat: '2026-07-14T10:00:00Z',
      created_at: '2026-07-14T09:00:00Z',
    },
    {
      id: 'd2',
      name: 'Device 2',
      serial: 'SN002',
      hostname: 'host2.local',
      os: 'macOS',
      org_unit_id: 'ou-test',
      status: 'offline',
      last_heartbeat: null,
      created_at: '2026-07-14T08:00:00Z',
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders heading and description', () => {
    mockWaddleperf.listDevices.mockResolvedValueOnce([]);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <DevicesPage />
      </QueryClientProvider>
    );

    expect(screen.getByText('Devices')).toBeInTheDocument();
    expect(
      screen.getByText('Manage and monitor WaddlePerf cluster devices')
    ).toBeInTheDocument();
  });

  it('renders devices in table', async () => {
    mockWaddleperf.listDevices.mockResolvedValueOnce(mockDevices);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <DevicesPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Device 1')).toBeInTheDocument();
    });
    expect(screen.getByText('Device 2')).toBeInTheDocument();
    expect(screen.getByText('ou-prod')).toBeInTheDocument();
  });

  it('shows empty state when no devices', async () => {
    mockWaddleperf.listDevices.mockResolvedValueOnce([]);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <DevicesPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('No data available')).toBeInTheDocument();
    });
  });

  it('shows error state on fetch failure', async () => {
    mockWaddleperf.listDevices.mockRejectedValueOnce(
      new Error('Network error')
    );

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <DevicesPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Error loading data')).toBeInTheDocument();
    });
    expect(screen.getByText('Network error')).toBeInTheDocument();
  });

  it('renders status badges', async () => {
    mockWaddleperf.listDevices.mockResolvedValueOnce(mockDevices);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <DevicesPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('online')).toBeInTheDocument();
    });
    expect(screen.getByText('offline')).toBeInTheDocument();
  });

  it('renders unknown status badge', async () => {
    const devicesWithUnknown: waddleperf.Device[] = [
      {
        id: 'd3',
        name: 'Device 3',
        serial: 'SN003',
        hostname: 'host3.local',
        os: 'Windows',
        org_unit_id: 'ou-staging',
        status: 'unknown',
        last_heartbeat: '2026-07-14T12:00:00Z',
        created_at: '2026-07-14T07:00:00Z',
      },
    ];

    mockWaddleperf.listDevices.mockResolvedValueOnce(devicesWithUnknown);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <DevicesPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('unknown')).toBeInTheDocument();
    });
  });

  it('formats null last_heartbeat as Never', async () => {
    const devicesWithNullHeartbeat: waddleperf.Device[] = [
      {
        id: 'd4',
        name: 'Device 4',
        serial: 'SN004',
        hostname: 'host4.local',
        os: 'Linux',
        org_unit_id: 'ou-prod',
        status: 'offline',
        last_heartbeat: null,
        created_at: '2026-07-14T06:00:00Z',
      },
    ];

    mockWaddleperf.listDevices.mockResolvedValueOnce(devicesWithNullHeartbeat);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <DevicesPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Never')).toBeInTheDocument();
    });
  });

  it('calls retry on fetch failure', async () => {
    const error = new Error('Network error');
    mockWaddleperf.listDevices.mockRejectedValueOnce(error);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <DevicesPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Error loading data')).toBeInTheDocument();
    });

    mockWaddleperf.listDevices.mockResolvedValueOnce(mockDevices);
    const retryButton = screen.getByText('Retry');
    await userEvent.click(retryButton);

    await waitFor(() => {
      expect(screen.getByText('Device 1')).toBeInTheDocument();
    });
  });
});
