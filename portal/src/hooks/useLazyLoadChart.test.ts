import React from 'react';
import { useLazyLoadChart } from './useLazyLoadChart';

jest.mock('../components/LiveChart', () => ({
  __esModule: true,
  default: jest.fn(() => React.createElement('div', { 'data-testid': 'chart' })),
}));

describe('useLazyLoadChart', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('returns a lazy-loaded chart component', () => {
    const chart = useLazyLoadChart();
    expect(chart).toBeDefined();
    expect(chart).not.toBeNull();
  });

  it('returns a ComponentType', () => {
    const chart = useLazyLoadChart();
    expect(typeof chart).toBe('object');
  });

  it('returns valid component on multiple calls', () => {
    const chart1 = useLazyLoadChart();
    const chart2 = useLazyLoadChart();
    expect(chart1).toBeDefined();
    expect(chart2).toBeDefined();
  });
});
