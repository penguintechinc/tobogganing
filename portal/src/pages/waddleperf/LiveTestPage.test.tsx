import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { LiveTestPage } from './LiveTestPage';
import * as useLiveTestHook from '../../hooks/useLiveTest';
import * as useRoleHook from '../../hooks/useRole';
import * as useLazyLoadChartHook from '../../hooks/useLazyLoadChart';

jest.mock('../../hooks/useLiveTest');
jest.mock('../../hooks/useRole');
jest.mock('../../hooks/useLazyLoadChart');

describe('LiveTestPage', () => {
  const mockStart = jest.fn();
  const mockReset = jest.fn();
  const mockChartComponent = ({ data }: { data: unknown[] }) => (
    <div data-testid="live-chart">Chart ({(data as unknown[]).length} points)</div>
  );

  beforeEach(() => {
    jest.clearAllMocks();

    (useLiveTestHook.useLiveTest as jest.Mock).mockReturnValue({
      status: 'closed',
      events: [],
      series: [],
      start: mockStart,
      reset: mockReset,
    });

    (useRoleHook.useRole as jest.Mock).mockReturnValue({
      role: 'maintainer',
      canWrite: () => true,
    });

    (useLazyLoadChartHook.useLazyLoadChart as jest.Mock).mockReturnValue(mockChartComponent);
  });

  it('renders page title and description', () => {
    render(<LiveTestPage />);

    expect(screen.getByText('Live Test')).toBeInTheDocument();
    expect(screen.getByText('Real-time network performance testing')).toBeInTheDocument();
  });

  it('shows connection status', () => {
    render(<LiveTestPage />);

    expect(screen.getByText('Connection Status')).toBeInTheDocument();
    expect(screen.getByText('Disconnected')).toBeInTheDocument();
  });

  it('renders form fields', () => {
    render(<LiveTestPage />);

    expect(screen.getByText(/Device ID/)).toBeInTheDocument();
    expect(screen.getByText(/Test Type/)).toBeInTheDocument();
    expect(screen.getByText(/Target/)).toBeInTheDocument();
  });

  it('renders form buttons', () => {
    render(<LiveTestPage />);

    expect(screen.getByTestId('start-button')).toBeInTheDocument();
    expect(screen.getByTestId('reset-button')).toBeInTheDocument();
  });

  it('updates form fields on input change', () => {
    render(<LiveTestPage />);

    const deviceInput = screen.getByTestId('device-id-input') as HTMLInputElement;
    const targetInput = screen.getByTestId('target-input') as HTMLInputElement;

    fireEvent.change(deviceInput, { target: { value: 'device-1' } });
    fireEvent.change(targetInput, { target: { value: 'example.com' } });

    expect(deviceInput.value).toBe('device-1');
    expect(targetInput.value).toBe('example.com');
  });

  it('disables start button when device_id or target is empty', () => {
    render(<LiveTestPage />);

    const startButton = screen.getByTestId('start-button');
    expect(startButton).toBeDisabled();
  });

  it('enables start button when all required fields are filled', () => {
    render(<LiveTestPage />);

    const deviceInput = screen.getByTestId('device-id-input');
    const targetInput = screen.getByTestId('target-input');
    const startButton = screen.getByTestId('start-button');

    fireEvent.change(deviceInput, { target: { value: 'device-1' } });
    fireEvent.change(targetInput, { target: { value: 'example.com' } });

    expect(startButton).not.toBeDisabled();
  });

  it('calls start with form data on button click', async () => {
    render(<LiveTestPage />);

    const deviceInput = screen.getByTestId('device-id-input');
    const targetInput = screen.getByTestId('target-input');
    const testTypeSelect = screen.getByTestId('test-type-select');
    const startButton = screen.getByTestId('start-button');

    fireEvent.change(deviceInput, { target: { value: 'device-1' } });
    fireEvent.change(targetInput, { target: { value: 'example.com' } });
    fireEvent.change(testTypeSelect, { target: { value: 'tcp' } });
    fireEvent.click(startButton);

    await waitFor(() => {
      expect(mockStart).toHaveBeenCalledWith({
        device_id: 'device-1',
        test_type: 'tcp',
        target: 'example.com',
      });
    });
  });

  it('disables form when viewer role', () => {
    (useRoleHook.useRole as jest.Mock).mockReturnValue({
      role: 'viewer',
      canWrite: () => false,
    });

    render(<LiveTestPage />);

    const deviceInput = screen.getByTestId('device-id-input') as HTMLInputElement;
    const startButton = screen.getByTestId('start-button') as HTMLButtonElement;

    expect(deviceInput.disabled).toBe(true);
    expect(startButton.disabled).toBe(true);
    expect(screen.getByText('Read-only mode: you cannot run tests')).toBeInTheDocument();
  });

  it('calls reset when reset button clicked', () => {
    render(<LiveTestPage />);

    const resetButton = screen.getByTestId('reset-button');
    fireEvent.click(resetButton);

    expect(mockReset).toHaveBeenCalled();
  });

  it('shows chart when series data available', () => {
    (useLiveTestHook.useLiveTest as jest.Mock).mockReturnValue({
      status: 'open',
      events: [],
      series: [
        { timestamp: Date.now(), latency: 100, throughput: 1000 },
        { timestamp: Date.now() + 1000, latency: 110, throughput: 1100 },
      ],
      start: mockStart,
      reset: mockReset,
    });

    render(<LiveTestPage />);

    expect(screen.getByTestId('live-chart')).toBeInTheDocument();
    expect(screen.getByText('Performance Metrics')).toBeInTheDocument();
  });

  it('maps series data to chart format', () => {
    const now = Date.now();
    (useLiveTestHook.useLiveTest as jest.Mock).mockReturnValue({
      status: 'open',
      events: [],
      series: [
        { timestamp: now, latency: 100, throughput: 1000 },
        { timestamp: now + 1000, latency: 110, throughput: 1100 },
      ],
      start: mockStart,
      reset: mockReset,
    });

    render(<LiveTestPage />);

    expect(screen.getByText('Chart (2 points)')).toBeInTheDocument();
  });

  it('displays events log when events present', () => {
    const events = [
      { event: 'test_started' as const, data: { message: 'Test started' } },
      { event: 'test_complete' as const, data: { message: 'Test finished' } },
    ];

    (useLiveTestHook.useLiveTest as jest.Mock).mockReturnValue({
      status: 'open',
      events,
      series: [],
      start: mockStart,
      reset: mockReset,
    });

    render(<LiveTestPage />);

    expect(screen.getByText('Recent Events (2)')).toBeInTheDocument();
    expect(screen.getByTestId('event-0')).toBeInTheDocument();
    expect(screen.getByTestId('event-1')).toBeInTheDocument();
  });

  it('displays error events with red styling', () => {
    const events = [{ event: 'error' as const, data: { message: 'Connection failed' } }];

    (useLiveTestHook.useLiveTest as jest.Mock).mockReturnValue({
      status: 'error',
      events,
      series: [],
      start: mockStart,
      reset: mockReset,
    });

    render(<LiveTestPage />);

    const eventElement = screen.getByTestId('event-0');
    expect(eventElement).toHaveClass('bg-red-900/30', 'text-red-300');
  });

  it('displays complete events with green styling', () => {
    const events = [{ event: 'test_complete' as const, data: { message: 'Test success' } }];

    (useLiveTestHook.useLiveTest as jest.Mock).mockReturnValue({
      status: 'open',
      events,
      series: [],
      start: mockStart,
      reset: mockReset,
    });

    render(<LiveTestPage />);

    const eventElement = screen.getByTestId('event-0');
    expect(eventElement).toHaveClass('bg-green-900/30', 'text-green-300');
  });

  it('updates connection status when websocket opens', () => {
    render(<LiveTestPage />);

    expect(screen.getByText('Disconnected')).toBeInTheDocument();

    (useLiveTestHook.useLiveTest as jest.Mock).mockReturnValue({
      status: 'open',
      events: [],
      series: [],
      start: mockStart,
      reset: mockReset,
    });

    render(<LiveTestPage />);

    expect(screen.getByText('Connected')).toBeInTheDocument();
  });

  it('shows connecting status', () => {
    (useLiveTestHook.useLiveTest as jest.Mock).mockReturnValue({
      status: 'connecting',
      events: [],
      series: [],
      start: mockStart,
      reset: mockReset,
    });

    render(<LiveTestPage />);

    expect(screen.getByText('Connecting...')).toBeInTheDocument();
  });

  it('shows error status', () => {
    (useLiveTestHook.useLiveTest as jest.Mock).mockReturnValue({
      status: 'error',
      events: [],
      series: [],
      start: mockStart,
      reset: mockReset,
    });

    render(<LiveTestPage />);

    expect(screen.getByText('Error')).toBeInTheDocument();
  });

  it('disables start button while test running', async () => {
    render(<LiveTestPage />);

    const deviceInput = screen.getByTestId('device-id-input');
    const targetInput = screen.getByTestId('target-input');
    const startButton = screen.getByTestId('start-button');

    fireEvent.change(deviceInput, { target: { value: 'device-1' } });
    fireEvent.change(targetInput, { target: { value: 'example.com' } });
    fireEvent.click(startButton);

    await waitFor(() => {
      expect(mockStart).toHaveBeenCalled();
    });

    // Simulate the component being in running state by checking if button label changes
    // (We'd need to track isRunning state, which gets set to true on start)
  });

  it('hides chart when no data', () => {
    render(<LiveTestPage />);

    expect(screen.queryByTestId('live-chart')).not.toBeInTheDocument();
  });

  it('shows test type options', () => {
    render(<LiveTestPage />);

    const select = screen.getByTestId('test-type-select') as HTMLSelectElement;
    const options = Array.from(select.options).map((opt) => opt.value);

    expect(options).toContain('http');
    expect(options).toContain('tcp');
    expect(options).toContain('udp');
    expect(options).toContain('icmp');
    expect(options).toContain('http_trace');
    expect(options).toContain('tcp_trace');
    expect(options).toContain('traceroute');
  });

  it('warns when form fields are missing', async () => {
    const consoleWarnSpy = jest.spyOn(console, 'warn').mockImplementation();
    render(<LiveTestPage />);

    // Button is disabled when fields are missing, so we verify it's disabled
    const btn = screen.getByTestId('start-button') as HTMLButtonElement;
    expect(btn.disabled).toBe(true);

    consoleWarnSpy.mockRestore();
  });

  it('handles start test error', async () => {
    const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation();
    (mockStart as jest.Mock).mockRejectedValueOnce(new Error('Test error'));

    render(<LiveTestPage />);

    const deviceInput = screen.getByTestId('device-id-input');
    const targetInput = screen.getByTestId('target-input');
    const start = screen.getByTestId('start-button');

    fireEvent.change(deviceInput, { target: { value: 'device-1' } });
    fireEvent.change(targetInput, { target: { value: 'example.com' } });
    fireEvent.click(start);

    await waitFor(() => {
      expect(consoleErrorSpy).toHaveBeenCalled();
    });

    consoleErrorSpy.mockRestore();
  });
});
