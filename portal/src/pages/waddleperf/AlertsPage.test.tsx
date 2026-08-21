import React from 'react';
import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AlertsPage } from './AlertsPage';
import * as wpcOps from '../../api/wpcOps';
import { useRole } from '../../hooks/useRole';

jest.mock('../../api/wpcOps');
jest.mock('../../hooks/useRole', () => ({ useRole: jest.fn() }));

const mockUseRole = useRole as jest.Mock;

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
  {
    id: 'ch-2',
    name: 'Slack Hook',
    kind: 'webhook',
    config: { url: 'https://hooks.slack.com/...' },
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
  {
    id: 'evt-2',
    rule_id: 'rule-1',
    device_id: 'dev-1',
    observed_value: 450,
    fired_at: '2026-07-15T11:00:00Z',
    notified: false,
  },
];

describe('AlertsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (wpcOps.listAlertRules as jest.Mock).mockResolvedValue(mockRules);
    (wpcOps.listAlertChannels as jest.Mock).mockResolvedValue(mockChannels);
    (wpcOps.listAlertEvents as jest.Mock).mockResolvedValue(mockEvents);
    (wpcOps.createAlertRule as jest.Mock).mockResolvedValue({ id: 'rule-2', ...mockRules[0] });
    (wpcOps.createAlertChannel as jest.Mock).mockResolvedValue({ id: 'ch-3', ...mockChannels[0] });
    (wpcOps.deleteAlertRule as jest.Mock).mockResolvedValue(undefined);
    (wpcOps.deleteAlertChannel as jest.Mock).mockResolvedValue(undefined);
    mockUseRole.mockReturnValue({ role: 'admin', canWrite: () => true });
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

  it('hides Add Rule button for viewers', async () => {
    mockUseRole.mockReturnValue({ role: 'viewer', canWrite: () => false });

    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AlertsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.queryByText('Add Rule')).not.toBeInTheDocument();
    });
  });

  it('toggles rule form visibility', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AlertsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Add Rule')).toBeInTheDocument();
    });

    const addBtn = screen.getByText('Add Rule');
    await userEvent.click(addBtn);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Rule name')).toBeInTheDocument();
    });

    const cancelBtn = screen.getByText('Cancel');
    await userEvent.click(cancelBtn);

    await waitFor(() => {
      expect(screen.queryByPlaceholderText('Rule name')).not.toBeInTheDocument();
    });
  });

  it('submits create rule form', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AlertsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Add Rule')).toBeInTheDocument();
    });

    const addBtn = screen.getByText('Add Rule');
    await userEvent.click(addBtn);

    const nameInput = screen.getByPlaceholderText('Rule name');
    const metricInput = screen.getByPlaceholderText('Metric (e.g., latency_ms)');
    const thresholdInput = screen.getByPlaceholderText('Threshold value');

    await userEvent.type(nameInput, 'High Error Rate');
    await userEvent.type(metricInput, 'error_rate');
    await userEvent.type(thresholdInput, '0.05');

    const comparatorSelect = screen.getByDisplayValue('Select operator');
    await userEvent.selectOptions(comparatorSelect, 'gt');

    // Submit the form directly — jsdom's constraint-validation handling of
    // number inputs is unreliable under userEvent.click; the handler and
    // payload assembly are what this test verifies.
    const form = document.querySelector('form');
    expect(form).not.toBeNull();
    fireEvent.submit(form as HTMLFormElement);

    await waitFor(() => {
      expect(wpcOps.createAlertRule).toHaveBeenCalledWith({
        name: 'High Error Rate',
        metric: 'error_rate',
        comparator: 'gt',
        threshold: 0.05,
        window_seconds: 300,
      });
    });
  });

  it('deletes alert rule', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AlertsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('High Latency')).toBeInTheDocument();
    });

    const deleteBtn = screen.getByText('Delete');
    await userEvent.click(deleteBtn);

    await waitFor(() => {
      expect(wpcOps.deleteAlertRule).toHaveBeenCalledWith('rule-1');
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
    await userEvent.click(channelsTab);

    await waitFor(() => {
      expect(screen.getByText('Default Email')).toBeInTheDocument();
      expect(screen.getByText('Slack Hook')).toBeInTheDocument();
    });
  });

  it('toggles channel form visibility', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AlertsPage />
      </QueryClientProvider>
    );

    const channelsTab = screen.getByText('Channels');
    await userEvent.click(channelsTab);

    await waitFor(() => {
      expect(screen.getByText('Default Email')).toBeInTheDocument();
    });

    const addBtn = screen.getByText('Add Channel');
    await userEvent.click(addBtn);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Channel name')).toBeInTheDocument();
    });

    const cancelBtn = screen.getByText('Cancel');
    await userEvent.click(cancelBtn);

    await waitFor(() => {
      expect(screen.queryByPlaceholderText('Channel name')).not.toBeInTheDocument();
    });
  });

  it('submits create channel form for email', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AlertsPage />
      </QueryClientProvider>
    );

    const channelsTab = screen.getByText('Channels');
    await userEvent.click(channelsTab);

    await waitFor(() => {
      expect(screen.getByText('Default Email')).toBeInTheDocument();
    });

    const addBtn = screen.getByText('Add Channel');
    await userEvent.click(addBtn);

    const nameInput = screen.getByPlaceholderText('Channel name');
    const kindSelect = screen.getByDisplayValue('Select type');
    const emailInput = screen.getByPlaceholderText('Email address');

    await userEvent.type(nameInput, 'Support Email');
    await userEvent.selectOptions(kindSelect, 'email');
    await userEvent.type(emailInput, 'support@example.com');

    const createBtn = screen.getByRole('button', { name: 'Create' });
    await userEvent.click(createBtn);

    await waitFor(() => {
      expect(wpcOps.createAlertChannel).toHaveBeenCalledWith({
        name: 'Support Email',
        kind: 'email',
        config: { to: ['support@example.com'] },
      });
    });
  });

  it('submits create channel form for webhook', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AlertsPage />
      </QueryClientProvider>
    );

    const channelsTab = screen.getByText('Channels');
    await userEvent.click(channelsTab);

    await waitFor(() => {
      expect(screen.getByText('Default Email')).toBeInTheDocument();
    });

    const addBtn = screen.getByText('Add Channel');
    await userEvent.click(addBtn);

    const nameInput = screen.getByPlaceholderText('Channel name');
    const kindSelect = screen.getByDisplayValue('Select type');
    const webhookInput = screen.getByPlaceholderText('Webhook URL');

    await userEvent.type(nameInput, 'Teams Webhook');
    await userEvent.selectOptions(kindSelect, 'webhook');
    await userEvent.type(webhookInput, 'https://outlook.webhook.office.com/...');

    const createBtn = screen.getByRole('button', { name: 'Create' });
    await userEvent.click(createBtn);

    await waitFor(() => {
      expect(wpcOps.createAlertChannel).toHaveBeenCalledWith({
        name: 'Teams Webhook',
        kind: 'webhook',
        config: { url: 'https://outlook.webhook.office.com/...' },
      });
    });
  });

  it('deletes alert channel', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AlertsPage />
      </QueryClientProvider>
    );

    const channelsTab = screen.getByText('Channels');
    await userEvent.click(channelsTab);

    await waitFor(() => {
      expect(screen.getByText('Default Email')).toBeInTheDocument();
    });

    const deleteButtons = screen.getAllByText('Delete');
    await userEvent.click(deleteButtons[0]!);

    await waitFor(() => {
      expect(wpcOps.deleteAlertChannel).toHaveBeenCalledWith('ch-1');
    });
  });

  it('displays webhook channel type', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AlertsPage />
      </QueryClientProvider>
    );

    const channelsTab = screen.getByText('Channels');
    await userEvent.click(channelsTab);

    await waitFor(() => {
      expect(screen.getByText('Webhook')).toBeInTheDocument();
    });
  });

  it('handles 402 license error when creating channel', async () => {
    const error = new Error('License required');
    Object.defineProperty(error, 'response', {
      value: {
        status: 402,
        data: { message: 'Webhook notifications require Professional tier' },
      },
      writable: false,
    });

    (wpcOps.createAlertChannel as jest.Mock).mockRejectedValueOnce(error);

    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AlertsPage />
      </QueryClientProvider>
    );

    const channelsTab = screen.getByText('Channels');
    await userEvent.click(channelsTab);

    await waitFor(() => {
      expect(screen.getByText('Default Email')).toBeInTheDocument();
    });

    const addBtn = screen.getByText('Add Channel');
    await userEvent.click(addBtn);

    const nameInput = screen.getByPlaceholderText('Channel name');
    const kindSelect = screen.getByDisplayValue('Select type');
    const webhookInput = screen.getByPlaceholderText('Webhook URL');

    await userEvent.type(nameInput, 'Premium Webhook');
    await userEvent.selectOptions(kindSelect, 'webhook');
    await userEvent.type(webhookInput, 'https://example.com/webhook');

    const createBtn = screen.getByRole('button', { name: 'Create' });
    await userEvent.click(createBtn);

    await waitFor(() => {
      expect(screen.getByText('Professional License Required')).toBeInTheDocument();
      expect(
        screen.getByText('Webhook notifications require Professional tier')
      ).toBeInTheDocument();
    });
  });

  it('switches to Events tab and displays events', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AlertsPage />
      </QueryClientProvider>
    );

    const eventsTab = screen.getByText('Events');
    await userEvent.click(eventsTab);

    await waitFor(() => {
      expect(screen.getAllByText('dev-1').length).toBeGreaterThan(0);
    });

    expect(screen.getAllByText('Yes').length).toBeGreaterThan(0);
    expect(screen.getAllByText('No').length).toBeGreaterThan(0);
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
});
