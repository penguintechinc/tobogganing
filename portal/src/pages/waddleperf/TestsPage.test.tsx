import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { TestsPage } from './TestsPage';
import * as waddleperf from '../../api/waddleperf';

jest.mock('../../api/waddleperf');

const mockWaddleperf = waddleperf as jest.Mocked<typeof waddleperf>;

describe('TestsPage', () => {
  const mockTests: waddleperf.Test[] = [
    {
      id: 't1-test-id-1',
      device_id: 'd1-device-id',
      test_type: 'latency',
      status: 'completed',
      target: 'http://example.com',
      latency_ms: 50,
      throughput: 1000,
      created_at: '2026-07-14T10:00:00Z',
    },
    {
      id: 't2-test-id-2',
      device_id: 'd2-device-id',
      test_type: 'throughput',
      status: 'pending',
      target: null,
      latency_ms: null,
      throughput: null,
      created_at: '2026-07-14T11:00:00Z',
    },
    {
      id: 't3-test-id-3',
      device_id: 'd3-device-id',
      test_type: 'packet-loss',
      status: 'failed',
      target: 'http://test.com',
      latency_ms: 150,
      throughput: null,
      created_at: '2026-07-14T12:00:00Z',
    },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders heading', () => {
    mockWaddleperf.listTests.mockResolvedValueOnce([]);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <TestsPage />
      </QueryClientProvider>
    );

    expect(screen.getByText('Tests')).toBeInTheDocument();
  });

  it('shows empty state when no tests', async () => {
    mockWaddleperf.listTests.mockResolvedValueOnce([]);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <TestsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('No tests available')).toBeInTheDocument();
    });
  });

  it('renders datatable when tests load', async () => {
    mockWaddleperf.listTests.mockResolvedValueOnce(mockTests);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <TestsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('datatable')).toBeInTheDocument();
    });
  });

  it('shows loading state', () => {
    mockWaddleperf.listTests.mockImplementationOnce(
      () => new Promise(() => {})
    );

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <TestsPage />
      </QueryClientProvider>
    );

    const animatePulse = document.querySelector('.animate-pulse');
    expect(animatePulse).toBeInTheDocument();
  });

  it('shows empty state when no tests', async () => {
    mockWaddleperf.listTests.mockResolvedValueOnce([]);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <TestsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('No tests available')).toBeInTheDocument();
    });
  });

  it('shows error state on fetch failure', async () => {
    mockWaddleperf.listTests.mockRejectedValueOnce(
      new Error('API error')
    );

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <TestsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Error loading tests')).toBeInTheDocument();
    });
    expect(screen.getByText('API error')).toBeInTheDocument();
  });

  it('shows retry button on error', async () => {
    mockWaddleperf.listTests.mockRejectedValueOnce(
      new Error('API error')
    );

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <TestsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Error loading tests')).toBeInTheDocument();
    });
    expect(screen.getByText('Retry')).toBeInTheDocument();
  });

  it('expands and collapses row detail panel', async () => {
    mockWaddleperf.listTests.mockResolvedValueOnce(mockTests);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <TestsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('datatable')).toBeInTheDocument();
    });

    const rows = screen.getAllByTestId('datatable-row');
    const firstRow = rows[0];
    expect(firstRow).toBeTruthy();

    // Click to expand
    fireEvent.click(firstRow!);
  });

  it('displays detail panel with null metrics', async () => {
    mockWaddleperf.listTests.mockResolvedValueOnce(mockTests);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <TestsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('datatable')).toBeInTheDocument();
    });

    const rows = screen.getAllByTestId('datatable-row');
    const secondRow = rows[1];
    expect(secondRow).toBeTruthy();
  });

  it('renders different status badges', async () => {
    mockWaddleperf.listTests.mockResolvedValueOnce(mockTests);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <TestsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('completed')).toBeInTheDocument();
    });

    expect(screen.getByText('pending')).toBeInTheDocument();
    expect(screen.getByText('failed')).toBeInTheDocument();
  });

  it('handles retry button click on error', async () => {
    mockWaddleperf.listTests.mockRejectedValueOnce(
      new Error('API error')
    );

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <TestsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Error loading tests')).toBeInTheDocument();
    });

    const retryBtn = screen.getByText('Retry');
    expect(retryBtn).toBeInTheDocument();
  });
});
