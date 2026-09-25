import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AutoCheckInsPage } from './AutoCheckInsPage';
import * as wpcOps from '../../api/wpcOps';
import { useRole } from '../../hooks/useRole';

jest.mock('../../api/wpcOps');
jest.mock('../../hooks/useRole', () => ({ useRole: jest.fn() }));

const mockUseRole = useRole as jest.Mock;

const createQueryClient = () =>
  new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

const mockCheckins: wpcOps.AutoCheckIn[] = [
  {
    id: 'checkin-1',
    tenant: 'tenant-1',
    name: 'Wifi Baseline',
    device_id: 'dev-1',
    target_kind: 'external',
    target: 'example.com',
    test_types: ['http_trace', 'traceroute', 'udp', 'http2'],
    interval_minutes: 5,
    jitter_pct: 10,
    samples_per_run: 2,
    threshold_stddev_min: null,
    threshold_stddev_max: 50,
    threshold_mean: null,
    tier: 1,
    parent_checkin_id: null,
    enabled: true,
    created_at: '2026-08-28T00:00:00Z',
    updated_at: '2026-08-28T00:00:00Z',
  },
];

const mockState: wpcOps.AutoCheckInState = {
  checkin_id: 'checkin-1',
  last_breached: false,
  last_mean_latency_ms: 12.5,
  last_stddev_latency_ms: 1.2,
  last_run_at: '2026-08-28T00:05:00Z',
  updated_at: '2026-08-28T00:05:00Z',
};

describe('AutoCheckInsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (wpcOps.listAutoCheckIns as jest.Mock).mockResolvedValue(mockCheckins);
    (wpcOps.getAutoCheckInState as jest.Mock).mockResolvedValue(mockState);
    mockUseRole.mockReturnValue({ role: 'admin', canWrite: () => true });
  });

  it('renders the page title', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoCheckInsPage />
      </QueryClientProvider>
    );
    expect(await screen.findByText('Auto Check-ins')).toBeInTheDocument();
  });

  it('lists check-ins with their tier badge', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoCheckInsPage />
      </QueryClientProvider>
    );
    expect(await screen.findByText('Wifi Baseline')).toBeInTheDocument();
    expect(screen.getByText('T1')).toBeInTheDocument();
  });

  it('creates a check-in via the form', async () => {
    (wpcOps.createAutoCheckIn as jest.Mock).mockResolvedValue({
      ...mockCheckins[0],
      id: 'checkin-2',
      name: 'New Checkin',
    });
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoCheckInsPage />
      </QueryClientProvider>
    );
    await userEvent.click(await screen.findByText('Create Check-in'));
    await userEvent.type(screen.getByPlaceholderText('Check-in name'), 'New Checkin');
    await userEvent.type(screen.getByPlaceholderText('Source device ID'), 'dev-2');
    await userEvent.type(screen.getByPlaceholderText('Target (URL/host:port)'), 'test.example.com');
    await userEvent.click(screen.getByText('Create'));

    await waitFor(() => expect(wpcOps.createAutoCheckIn).toHaveBeenCalled());
  });

  it('deletes a check-in', async () => {
    (wpcOps.deleteAutoCheckIn as jest.Mock).mockResolvedValue(undefined);
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoCheckInsPage />
      </QueryClientProvider>
    );
    await userEvent.click(await screen.findByText('Delete'));
    await waitFor(() => expect(wpcOps.deleteAutoCheckIn).toHaveBeenCalledWith('checkin-1'));
  });

  it('shows cascade state when expanded', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoCheckInsPage />
      </QueryClientProvider>
    );
    await userEvent.click(await screen.findByText('State'));
    expect(await screen.findByText(/Last Breached/)).toBeInTheDocument();
  });

  it('hides create/delete controls for read-only role', async () => {
    mockUseRole.mockReturnValue({ role: 'viewer', canWrite: () => false });
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoCheckInsPage />
      </QueryClientProvider>
    );
    await screen.findByText('Wifi Baseline');
    expect(screen.queryByText('Create Check-in')).not.toBeInTheDocument();
    expect(screen.queryByText('Delete')).not.toBeInTheDocument();
  });

  it('toggles state visibility for a read-only role', async () => {
    mockUseRole.mockReturnValue({ role: 'viewer', canWrite: () => false });
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoCheckInsPage />
      </QueryClientProvider>
    );
    const toggleButton = await screen.findByRole('button', {
      name: 'Toggle state for check-in checkin-1',
    });
    await userEvent.click(toggleButton);
    expect(await screen.findByText(/Last Breached/)).toBeInTheDocument();
    await userEvent.click(toggleButton);
    await waitFor(() => expect(screen.queryByText(/Last Breached/)).not.toBeInTheDocument());
  });

  it('retries loading check-ins on error', async () => {
    (wpcOps.listAutoCheckIns as jest.Mock).mockRejectedValueOnce(new Error('network error'));
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoCheckInsPage />
      </QueryClientProvider>
    );
    await userEvent.click(await screen.findByText('Retry'));
    await waitFor(() => expect(wpcOps.listAutoCheckIns).toHaveBeenCalledTimes(2));
    expect(await screen.findByText('Wifi Baseline')).toBeInTheDocument();
  });
});
