import { render, screen } from '@testing-library/react';
import LiveChart from './LiveChart';

jest.mock('recharts', () => ({
  LineChart: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="line-chart">{children}</div>
  ),
  Line: (props: { dataKey: string; name?: string }) => (
    <div data-testid={`line-${props.dataKey}`}>{props.name || props.dataKey}</div>
  ),
  XAxis: ({ dataKey }: { dataKey: string }) => <div data-testid="x-axis">{dataKey}</div>,
  YAxis: () => <div data-testid="y-axis" />,
  CartesianGrid: () => <div data-testid="cartesian-grid" />,
  Tooltip: () => <div data-testid="tooltip" />,
  Legend: () => <div data-testid="legend" />,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
}));

describe('LiveChart', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('renders no data message when empty', () => {
    render(<LiveChart data={[]} />);
    expect(screen.getByText('No data yet')).toBeInTheDocument();
  });

  it('renders chart with latency data', () => {
    const data = [
      { timestamp: '10:00:00', latency: 100 },
      { timestamp: '10:00:01', latency: 110 },
    ];

    render(<LiveChart data={data} />);

    expect(screen.getByTestId('line-chart')).toBeInTheDocument();
    expect(screen.getByTestId('line-latency')).toBeInTheDocument();
  });

  it('renders chart with throughput data', () => {
    const data = [
      { timestamp: '10:00:00', throughput: 1000 },
      { timestamp: '10:00:01', throughput: 1100 },
    ];

    render(<LiveChart data={data} />);

    expect(screen.getByTestId('line-chart')).toBeInTheDocument();
    expect(screen.getByTestId('line-throughput')).toBeInTheDocument();
  });

  it('renders chart with both latency and throughput', () => {
    const data = [
      { timestamp: '10:00:00', latency: 100, throughput: 1000 },
      { timestamp: '10:00:01', latency: 110, throughput: 1100 },
    ];

    render(<LiveChart data={data} />);

    expect(screen.getByTestId('line-latency')).toBeInTheDocument();
    expect(screen.getByTestId('line-throughput')).toBeInTheDocument();
  });

  it('renders ResponsiveContainer', () => {
    const data = [{ timestamp: '10:00:00', latency: 100 }];

    render(<LiveChart data={data} />);

    expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
  });

  it('renders axes and legend', () => {
    const data = [{ timestamp: '10:00:00', latency: 100, throughput: 1000 }];

    render(<LiveChart data={data} />);

    expect(screen.getByTestId('x-axis')).toBeInTheDocument();
    expect(screen.getByTestId('y-axis')).toBeInTheDocument();
    expect(screen.getByTestId('legend')).toBeInTheDocument();
  });

  it('skips latency line when no latency data', () => {
    const data = [{ timestamp: '10:00:00', throughput: 1000 }];

    render(<LiveChart data={data} />);

    expect(screen.queryByTestId('line-latency')).not.toBeInTheDocument();
    expect(screen.getByTestId('line-throughput')).toBeInTheDocument();
  });

  it('skips throughput line when no throughput data', () => {
    const data = [{ timestamp: '10:00:00', latency: 100 }];

    render(<LiveChart data={data} />);

    expect(screen.getByTestId('line-latency')).toBeInTheDocument();
    expect(screen.queryByTestId('line-throughput')).not.toBeInTheDocument();
  });

  it('logs render info', () => {
    const consoleSpy = jest.spyOn(console, 'log').mockImplementation();
    const data = [{ timestamp: '10:00:00', latency: 100 }];

    render(<LiveChart data={data} />);

    expect(consoleSpy).toHaveBeenCalledWith('[LiveChart] Render { points:', 1, '}');
    consoleSpy.mockRestore();
  });
});
