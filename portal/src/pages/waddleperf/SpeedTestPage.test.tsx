import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { SpeedTestPage } from './SpeedTestPage';
import * as useSpeedTestHook from '../../hooks/useSpeedTest';

jest.mock('../../hooks/useSpeedTest');
jest.mock('../../components/SpeedTestChart', () => ({
  __esModule: true,
  default: ({ data }: { data: unknown[] }) => (
    <div data-testid="speedtest-chart">Chart ({data.length} points)</div>
  ),
}));

describe('SpeedTestPage', () => {
  const mockRun = jest.fn();
  const mockReset = jest.fn();

  const baseState = {
    phase: 'idle' as const,
    ping: null,
    download: null,
    upload: null,
    series: [] as never[],
    error: null,
    run: mockRun,
    reset: mockReset,
  };

  beforeEach(() => {
    jest.clearAllMocks();
    (useSpeedTestHook.useSpeedTest as jest.Mock).mockReturnValue(baseState);
  });

  it('renders page title and description', () => {
    render(<SpeedTestPage />);

    expect(screen.getByText('Speed Test')).toBeInTheDocument();
    expect(screen.getByText('Run a self-service bandwidth and latency test')).toBeInTheDocument();
  });

  it('renders server URL input and control buttons', () => {
    render(<SpeedTestPage />);

    expect(screen.getByTestId('server-url-input')).toBeInTheDocument();
    expect(screen.getByTestId('start-button')).toBeInTheDocument();
    expect(screen.getByTestId('reset-button')).toBeInTheDocument();
  });

  it('shows placeholder metric values before a test runs', () => {
    render(<SpeedTestPage />);

    expect(screen.getAllByText('--')).toHaveLength(4);
  });

  it('updates server URL input on change', () => {
    render(<SpeedTestPage />);

    const input = screen.getByTestId('server-url-input') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'https://engine.example.com' } });

    expect(input.value).toBe('https://engine.example.com');
  });

  it('calls run with the entered server URL on start', async () => {
    render(<SpeedTestPage />);

    const input = screen.getByTestId('server-url-input');
    fireEvent.change(input, { target: { value: 'https://engine.example.com' } });
    fireEvent.click(screen.getByTestId('start-button'));

    await waitFor(() => {
      expect(mockRun).toHaveBeenCalledWith('https://engine.example.com');
    });
  });

  it('calls reset and clears the server URL field on reset click', () => {
    render(<SpeedTestPage />);

    const input = screen.getByTestId('server-url-input') as HTMLInputElement;
    fireEvent.change(input, { target: { value: 'https://engine.example.com' } });
    fireEvent.click(screen.getByTestId('reset-button'));

    expect(mockReset).toHaveBeenCalled();
    expect(input.value).toBe('');
  });

  it('disables inputs and shows running label while a phase is in progress', () => {
    (useSpeedTestHook.useSpeedTest as jest.Mock).mockReturnValue({
      ...baseState,
      phase: 'download',
    });

    render(<SpeedTestPage />);

    expect(screen.getByTestId('server-url-input')).toBeDisabled();
    expect(screen.getByTestId('start-button')).toBeDisabled();
    expect(screen.getByTestId('reset-button')).toBeDisabled();
    expect(screen.getByText('Measuring download...')).toBeInTheDocument();
  });

  it('renders ping/download/upload metrics once available', () => {
    (useSpeedTestHook.useSpeedTest as jest.Mock).mockReturnValue({
      ...baseState,
      phase: 'complete',
      ping: { latencyMs: 12.345, jitterMs: 1.2, samples: [12] },
      download: { mbps: 123.456, bytes: 1, durationMs: 1 },
      upload: { mbps: 45.6, bytes: 1, durationMs: 1 },
    });

    render(<SpeedTestPage />);

    expect(screen.getByText('12.3')).toBeInTheDocument();
    expect(screen.getByText('1.2')).toBeInTheDocument();
    expect(screen.getByText('123.46')).toBeInTheDocument();
    expect(screen.getByText('45.60')).toBeInTheDocument();
    expect(screen.getByText('Complete')).toBeInTheDocument();
  });

  it('shows the error message when the test fails', () => {
    (useSpeedTestHook.useSpeedTest as jest.Mock).mockReturnValue({
      ...baseState,
      phase: 'error',
      error: 'Speed test failed',
    });

    render(<SpeedTestPage />);

    expect(screen.getByTestId('error-message')).toHaveTextContent('Speed test failed');
    expect(screen.getByText('Error')).toBeInTheDocument();
  });

  it('renders the realtime chart once samples exist', async () => {
    (useSpeedTestHook.useSpeedTest as jest.Mock).mockReturnValue({
      ...baseState,
      phase: 'download',
      series: [
        { timestamp: Date.now(), label: 'download', mbps: 50 },
        { timestamp: Date.now(), label: 'download', mbps: 55 },
      ],
    });

    render(<SpeedTestPage />);

    expect(screen.getByText('Realtime Throughput')).toBeInTheDocument();
    // SpeedTestChart is React.lazy-loaded, so it resolves after a microtask.
    await waitFor(() => {
      expect(screen.getByTestId('speedtest-chart')).toBeInTheDocument();
    });
  });

  it('hides the chart section when there are no samples', () => {
    render(<SpeedTestPage />);

    expect(screen.queryByText('Realtime Throughput')).not.toBeInTheDocument();
  });
});
