import type { ComponentType } from 'react';
import { DevicesPage } from '../pages/waddleperf/DevicesPage';
import { TestsPage } from '../pages/waddleperf/TestsPage';
import { StatsPage } from '../pages/waddleperf/StatsPage';

/** View-slug -> page map for the waddleperf_cluster module. */
export const wpcViews: Record<string, ComponentType> = {
  devices: DevicesPage,
  tests: TestsPage,
  stats: StatsPage,
};
