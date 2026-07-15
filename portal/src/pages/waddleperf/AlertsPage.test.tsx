import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AlertsPage } from './AlertsPage';
import * as wpcOps from '../../api/wpcOps';

jest.mock('../../api/wpcOps');
jest.mock('../../hooks/useRole', () => ({
  useRole: () => ({ role: 'admin', canWrite: () => true }),
}));

const createQueryClient = () =>
  new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

const mockRules: wpcOps.AlertRule[] = [
  {
    id: 'rule-1',
    name: 'High Latency',
    metric: 'latency_ms',
    comparator: 'gt',
    threshold: 500,
    window_seconds: 300,
    enabled: true,
    created_at: '2026-07-15T00:00:00Z',
  },
];

const mockChannels: wpcOps.AlertChannel[] = [
  {
    id: 'ch-1',
    name: 'Default Email',
    kind: 'email',
    config: { to: ['admin@test.com'] },
    enabled: true,
    created_at: '2026-07-15T00:00:00Z',
  },
];

const mockEvents: wpcOps.AlertEvent[] = [
  {
    id: 'evt-1',
    rule_id: 'rule-1',
    device_id: 'dev-1',
    observed_value: 600,
    fired_at: '2026-07-15T10:00:00Z',
    notified: true,
  },
];

describe('AlertsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (wpcOps.listAlertRules as jest.Mock).mockResolvedValue(mockRules);
    (wpcOps.listAlertChannels as jest.Mock).mockResolvedValue(mockChannels);
    (wpcOps.listAlertEvents as jest.Mock).mockResolvedValue(mockEvents);
  });

  it('renders tabs', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AlertsPage />
      </QueryClientProvider>
    );

    expect(screen.getByText('Rules')).toBeInTheDocument();
    expect(screen.getByText('Channels')).toBeInTheDocument();
    expect(screen.getByText('Events')).toBeInTheDocument();
  });

  it('loads and displays rules', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AlertsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('High Latency')).toBeInTheDocument();
      expect(screen.getByText('latency_ms')).toBeInTheDocument();
    });
  });

  it('shows Add Rule button for authenticated users', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AlertsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Add Rule')).toBeInTheDocument();
    });
  });

  it('displays empty state when no data', async () => {
    (wpcOps.listAlertRules as jest.Mock).mockResolvedValue([]);
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AlertsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('No data available')).toBeInTheDocument();
    });
  });

  it('switches to Channels tab', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AlertsPage />
      </QueryClientProvider>
    );

    const channelsTab = screen.getByText('Channels');
    channelsTab.click();

    await waitFor(() => {
      expect(screen.getByText('Default Email')).toBeInTheDocument();
    });
  });

  it('switches to Events tab', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AlertsPage />
      </QueryClientProvider>
    );

    const eventsTab = screen.getByText('Events');
    eventsTab.click();

    await waitFor(() => {
      expect(screen.getByText('dev-1')).toBeInTheDocument();
    });
  });
});
