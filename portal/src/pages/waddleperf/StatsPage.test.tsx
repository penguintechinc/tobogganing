import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { StatsPage } from './StatsPage';
import * as waddleperf from '../../api/waddleperf';

jest.mock('../../api/waddleperf');
jest.mock('../../components/TrendsChart', () => ({
  __esModule: true,
  default: ({ data }: { data: Array<{ timestamp: string; value: number }> }) => (
    <div data-testid="trends-chart">Chart with {data.length} points</div>
  ),
}));

const mockWaddleperf = waddleperf as jest.Mocked<typeof waddleperf>;

describe('StatsPage', () => {
  const mockSummary: waddleperf.StatsSummary = {
    total_tests: 100,
    total_devices: 10,
    success_rate: 0.95,
    avg_latency_ms: 50,
    avg_throughput: 900,
  };

  const mockTrends: waddleperf.TrendDataPoint[] = [
    { timestamp: '2026-07-14T10:00:00Z', value: 95 },
    { timestamp: '2026-07-14T11:00:00Z', value: 94 },
  ];

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders heading and description', () => {
    mockWaddleperf.getStatsSummary.mockResolvedValueOnce(mockSummary);
    mockWaddleperf.getStatsTrends.mockResolvedValueOnce(mockTrends);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <StatsPage />
      </QueryClientProvider>
    );

    expect(screen.getByText('Statistics')).toBeInTheDocument();
    expect(
      screen.getByText('Overview of WaddlePerf cluster performance metrics')
    ).toBeInTheDocument();
  });

  it('renders summary cards', async () => {
    mockWaddleperf.getStatsSummary.mockResolvedValueOnce(mockSummary);
    mockWaddleperf.getStatsTrends.mockResolvedValueOnce(mockTrends);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <StatsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Total Tests')).toBeInTheDocument();
    });
    expect(screen.getByText('100')).toBeInTheDocument();
    expect(screen.getByText('Total Devices')).toBeInTheDocument();
    expect(screen.getByText('10')).toBeInTheDocument();
  });

  it('renders trends chart', async () => {
    mockWaddleperf.getStatsSummary.mockResolvedValueOnce(mockSummary);
    mockWaddleperf.getStatsTrends.mockResolvedValueOnce(mockTrends);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <StatsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByTestId('trends-chart')).toBeInTheDocument();
    });
  });

  it('shows error state on summary fetch failure', async () => {
    mockWaddleperf.getStatsSummary.mockRejectedValueOnce(new Error('Summary error'));
    mockWaddleperf.getStatsTrends.mockResolvedValueOnce(mockTrends);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <StatsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Error loading statistics')).toBeInTheDocument();
    });
    expect(screen.getByText('Summary error')).toBeInTheDocument();
  });

  it('renders loading state', () => {
    mockWaddleperf.getStatsSummary.mockImplementationOnce(() => new Promise(() => {}));
    mockWaddleperf.getStatsTrends.mockImplementationOnce(() => new Promise(() => {}));

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <StatsPage />
      </QueryClientProvider>
    );

    const animatePulse = document.querySelector('.animate-pulse');
    expect(animatePulse).toBeInTheDocument();
  });

  it('handles retry button click on error', async () => {
    mockWaddleperf.getStatsSummary.mockRejectedValueOnce(new Error('Summary error'));
    mockWaddleperf.getStatsTrends.mockResolvedValueOnce(mockTrends);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <StatsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Error loading statistics')).toBeInTheDocument();
    });

    const retryBtn = screen.getByText('Retry');
    expect(retryBtn).toBeInTheDocument();
  });

  it('shows error state on trends fetch failure', async () => {
    mockWaddleperf.getStatsSummary.mockResolvedValueOnce(mockSummary);
    mockWaddleperf.getStatsTrends.mockRejectedValueOnce(new Error('Trends error'));

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <StatsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Error loading statistics')).toBeInTheDocument();
    });
    expect(screen.getByText('Trends error')).toBeInTheDocument();
  });

  it('renders performance metrics', async () => {
    mockWaddleperf.getStatsSummary.mockResolvedValueOnce(mockSummary);
    mockWaddleperf.getStatsTrends.mockResolvedValueOnce(mockTrends);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <StatsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Success Rate')).toBeInTheDocument();
      expect(screen.getByText('95')).toBeInTheDocument();
      expect(screen.getByText('Avg Latency')).toBeInTheDocument();
      expect(screen.getByText('ms')).toBeInTheDocument();
    });
  });

  it('retries on error', async () => {
    mockWaddleperf.getStatsSummary.mockRejectedValueOnce(new Error('Summary error'));
    mockWaddleperf.getStatsTrends.mockResolvedValueOnce(mockTrends);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <StatsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Error loading statistics')).toBeInTheDocument();
    });

    mockWaddleperf.getStatsSummary.mockResolvedValueOnce(mockSummary);
    const retryBtn = screen.getByText('Retry');
    await userEvent.click(retryBtn);

    await waitFor(() => {
      expect(screen.getByText('Total Tests')).toBeInTheDocument();
    });
  });
});
