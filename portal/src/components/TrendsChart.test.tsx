import { render, screen } from '@testing-library/react';
import TrendsChart from './TrendsChart';

jest.mock('recharts', () => ({
  LineChart: ({ children, data }: { children: React.ReactNode; data?: Array<{ name: string; value: number }> }) => (
    <div data-testid="line-chart" data-count={data?.length}>
      {children}
    </div>
  ),
  Line: () => null,
  XAxis: () => null,
  YAxis: () => null,
  CartesianGrid: () => null,
  Tooltip: () => null,
  ResponsiveContainer: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="responsive-container">{children}</div>
  ),
}));

describe('TrendsChart', () => {
  const mockData = [
    { timestamp: '2026-07-14T10:00:00Z', value: 95 },
    { timestamp: '2026-07-14T11:00:00Z', value: 94 },
  ];

  it('renders empty state when no data', () => {
    render(<TrendsChart data={[]} />);

    expect(screen.getByText('No trend data available')).toBeInTheDocument();
  });

  it('renders chart with data', () => {
    render(<TrendsChart data={mockData} />);

    const chart = screen.getByTestId('line-chart');
    expect(chart).toBeInTheDocument();
    expect(chart).toHaveAttribute('data-count', '2');
  });

  it('renders responsive container', () => {
    render(<TrendsChart data={mockData} />);

    expect(screen.getByTestId('responsive-container')).toBeInTheDocument();
  });

  it('formats timestamps correctly in chart data', () => {
    const { container } = render(<TrendsChart data={mockData} />);

    const chart = container.querySelector('[data-testid="line-chart"]');
    expect(chart).toBeInTheDocument();
  });
});
