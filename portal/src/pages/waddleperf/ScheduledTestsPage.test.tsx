import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ScheduledTestsPage } from './ScheduledTestsPage';
import * as wpcOps from '../../api/wpcOps';
import { useRole } from '../../hooks/useRole';

jest.mock('../../api/wpcOps');
jest.mock('../../hooks/useRole', () => ({ useRole: jest.fn() }));

const mockUseRole = useRole as jest.Mock;

const createQueryClient = () =>
  new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

const mockTests: wpcOps.ScheduledTest[] = [
  {
    id: 'job-1',
    device_id: 'dev-1',
    test_type: 'latency',
    target: 'https://example.com',
    interval_seconds: 300,
    enabled: true,
    next_run_at: '2026-07-15T11:00:00Z',
    last_run_at: '2026-07-15T10:00:00Z',
    created_at: '2026-07-15T00:00:00Z',
  },
  {
    id: 'job-2',
    device_id: 'dev-2',
    test_type: 'throughput',
    target: 'https://api.example.com',
    interval_seconds: 600,
    enabled: false,
    next_run_at: '2026-07-15T12:00:00Z',
    last_run_at: '2026-07-15T10:30:00Z',
    created_at: '2026-07-15T01:00:00Z',
  },
];

describe('ScheduledTestsPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (wpcOps.listScheduledTests as jest.Mock).mockResolvedValue(mockTests);
    (wpcOps.createScheduledTest as jest.Mock).mockResolvedValue({ id: 'job-3', ...mockTests[0] });
    (wpcOps.updateScheduledTest as jest.Mock).mockResolvedValue({ id: 'job-1', ...mockTests[0], enabled: false });
    (wpcOps.deleteScheduledTest as jest.Mock).mockResolvedValue(undefined);
    mockUseRole.mockReturnValue({ role: 'admin', canWrite: () => true });
  });

  it('renders the page title', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ScheduledTestsPage />
      </QueryClientProvider>
    );

    expect(screen.getByText('Scheduled Tests')).toBeInTheDocument();
  });

  it('loads and displays scheduled tests', async () => {

    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ScheduledTestsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('dev-1')).toBeInTheDocument();
      expect(screen.getByText('latency')).toBeInTheDocument();
      expect(screen.getByText('dev-2')).toBeInTheDocument();
      expect(screen.getByText('throughput')).toBeInTheDocument();
    });
  });

  it('shows Create Test button for admin', async () => {

    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ScheduledTestsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Create Test')).toBeInTheDocument();
    });
  });

  it('hides Create Test button for viewers', async () => {
    mockUseRole.mockReturnValue({ role: 'viewer', canWrite: () => false });

    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ScheduledTestsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.queryByText('Create Test')).not.toBeInTheDocument();
    });
  });

  it('displays enable/disable and delete actions for admin', async () => {

    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ScheduledTestsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      const disableButtons = screen.getAllByText('Disable');
      const enableButtons = screen.getAllByText('Enable');
      expect(disableButtons.length).toBeGreaterThan(0);
      expect(enableButtons.length).toBeGreaterThan(0);
      expect(screen.getAllByText('Delete').length).toBeGreaterThan(0);
    });
  });

  it('toggles form visibility', async () => {

    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ScheduledTestsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Create Test')).toBeInTheDocument();
    });

    const createBtn = screen.getByText('Create Test');
    await userEvent.click(createBtn);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('Device ID')).toBeInTheDocument();
    });

    const cancelBtn = screen.getByText('Cancel');
    await userEvent.click(cancelBtn);

    await waitFor(() => {
      expect(screen.queryByPlaceholderText('Device ID')).not.toBeInTheDocument();
    });
  });

  it('submits create test form', async () => {

    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ScheduledTestsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Create Test')).toBeInTheDocument();
    });

    const createBtn = screen.getByText('Create Test');
    await userEvent.click(createBtn);

    const deviceInput = screen.getByPlaceholderText('Device ID');
    const typeInput = screen.getByPlaceholderText('Test type');
    const targetInput = screen.getByPlaceholderText('Target URL or endpoint');
    const intervalInput = screen.getByPlaceholderText('Interval (seconds, min 30)');

    await userEvent.type(deviceInput, 'dev-3');
    await userEvent.type(typeInput, 'jitter');
    await userEvent.type(targetInput, 'https://new.example.com');
    await userEvent.type(intervalInput, '600');

    const submitBtn = screen.getByRole('button', { name: 'Create' });
    await userEvent.click(submitBtn);

    await waitFor(() => {
      expect(wpcOps.createScheduledTest).toHaveBeenCalledWith({
        device_id: 'dev-3',
        test_type: 'jitter',
        target: 'https://new.example.com',
        interval_seconds: 600,
      });
    });
  });

  it('disables enabled test', async () => {

    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ScheduledTestsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('dev-1')).toBeInTheDocument();
    });

    const disableButtons = screen.getAllByText('Disable');
    await userEvent.click(disableButtons[0]!);

    await waitFor(() => {
      expect(wpcOps.updateScheduledTest).toHaveBeenCalledWith('job-1', { enabled: false });
    });
  });

  it('enables disabled test', async () => {

    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ScheduledTestsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('dev-2')).toBeInTheDocument();
    });

    const enableButtons = screen.getAllByText('Enable');
    await userEvent.click(enableButtons[0]!);

    await waitFor(() => {
      expect(wpcOps.updateScheduledTest).toHaveBeenCalledWith('job-2', { enabled: true });
    });
  });

  it('deletes scheduled test', async () => {

    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ScheduledTestsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('dev-1')).toBeInTheDocument();
    });

    const deleteButtons = screen.getAllByText('Delete');
    await userEvent.click(deleteButtons[0]!);

    await waitFor(() => {
      expect(wpcOps.deleteScheduledTest).toHaveBeenCalledWith('job-1');
    });
  });

  it('displays empty state when no tests', async () => {

    (wpcOps.listScheduledTests as jest.Mock).mockResolvedValue([]);
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ScheduledTestsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('No data available')).toBeInTheDocument();
    });
  });

  it('shows loading state', async () => {

    (wpcOps.listScheduledTests as jest.Mock).mockImplementation(() => new Promise(() => {}));
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ScheduledTestsPage />
      </QueryClientProvider>
    );

    expect(screen.getByTestId('datatable')).toBeInTheDocument();
  });

  it('hides actions for viewers', async () => {
    mockUseRole.mockReturnValue({ role: 'viewer', canWrite: () => false });

    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <ScheduledTestsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('dev-1')).toBeInTheDocument();
    });

    expect(screen.queryByText('Disable')).not.toBeInTheDocument();
    expect(screen.queryByText('Enable')).not.toBeInTheDocument();
    expect(screen.queryByText('Delete')).not.toBeInTheDocument();
  });
});
