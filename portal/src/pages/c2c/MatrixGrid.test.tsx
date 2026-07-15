import React from 'react';
import { render, screen } from '@testing-library/react';
import { MatrixGrid } from './MatrixGrid';
import { MatrixCell } from '../../api/c2c';

describe('MatrixGrid', () => {
  it('renders with header row and column headers', () => {
    const regions = ['us-west-2', 'us-east-1'];
    const cells = [
      {
        source: 'us-west-2',
        destination: 'us-east-1',
        loss_pct: 0.5,
        latency: 50,
        test_type: 'latency',
      },
    ];

    render(
      <MatrixGrid
        regions={regions}
        cells={cells}
        testType="latency"
      />
    );

    expect(screen.getByText('latency')).toBeInTheDocument();
    expect(screen.getAllByText('us-east-1').length).toBeGreaterThan(0);
    expect(screen.getAllByText('us-west-2').length).toBeGreaterThan(0);
  });

  it('colors cells based on loss percentage', () => {
    const regions = ['region-a', 'region-b'];
    const cells = [
      {
        source: 'region-a',
        destination: 'region-b',
        loss_pct: 0.5,
        latency: 50,
        test_type: 'latency',
      },
      {
        source: 'region-b',
        destination: 'region-a',
        loss_pct: 3.0,
        latency: 60,
        test_type: 'latency',
      },
    ];

    const { container } = render(
      <MatrixGrid
        regions={regions}
        cells={cells}
        testType="latency"
      />
    );

    const cells_dom = container.querySelectorAll('.bg-green-900, .bg-amber-900');
    expect(cells_dom.length).toBeGreaterThan(0);
  });

  it('displays latency and loss percentage', () => {
    const regions = ['region-a', 'region-b'];
    const cells = [
      {
        source: 'region-a',
        destination: 'region-b',
        loss_pct: 1.5,
        latency: 42.5,
        test_type: 'latency',
      },
    ];

    render(
      <MatrixGrid
        regions={regions}
        cells={cells}
        testType="latency"
      />
    );

    expect(screen.getByText('42.50ms')).toBeInTheDocument();
    expect(screen.getByText('1.5% loss')).toBeInTheDocument();
  });

  it('shows empty cell for missing pairs', () => {
    const regions = ['region-a', 'region-b'];
    const cells: MatrixCell[] = [];

    render(
      <MatrixGrid
        regions={regions}
        cells={cells}
        testType="latency"
      />
    );

    const emptyCells = screen.getAllByText('—');
    expect(emptyCells.length).toBeGreaterThan(0);
  });

  it('sorts regions alphabetically', () => {
    const regions = ['z-region', 'a-region', 'm-region'];
    const cells = [
      {
        source: 'a-region',
        destination: 'z-region',
        loss_pct: 0.5,
        latency: 50,
        test_type: 'latency',
      },
    ];

    const { container } = render(
      <MatrixGrid
        regions={regions}
        cells={cells}
        testType="latency"
      />
    );

    const headers = container.querySelectorAll('div');
    const regionHeaders = Array.from(headers)
      .filter((h) => h.textContent?.match(/region/))
      .map((h) => h.textContent);

    expect(regionHeaders.length).toBeGreaterThan(0);
  });

  it('applies red color for high loss', () => {
    const regions = ['region-a', 'region-b'];
    const cells = [
      {
        source: 'region-a',
        destination: 'region-b',
        loss_pct: 10.0,
        latency: 50,
        test_type: 'latency',
      },
    ];

    const { container } = render(
      <MatrixGrid
        regions={regions}
        cells={cells}
        testType="latency"
      />
    );

    const redCells = container.querySelectorAll('.bg-red-900');
    expect(redCells.length).toBeGreaterThan(0);
  });
});
