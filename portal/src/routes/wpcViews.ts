import type { ComponentType } from 'react';
import { DevicesPage } from '../pages/waddleperf/DevicesPage';
import { TestsPage } from '../pages/waddleperf/TestsPage';
import { StatsPage } from '../pages/waddleperf/StatsPage';
import { AlertsPage } from '../pages/waddleperf/AlertsPage';
import { ScheduledTestsPage } from '../pages/waddleperf/ScheduledTestsPage';
import { AutoPerfPage } from '../pages/waddleperf/AutoPerfPage';
import { LiveTestPage } from '../pages/waddleperf/LiveTestPage';

/** View-slug -> page map for the waddleperf_cluster module. */
export const wpcViews: Record<string, ComponentType> = {
  devices: DevicesPage,
  tests: TestsPage,
  stats: StatsPage,
  alerts: AlertsPage,
  'scheduled-tests': ScheduledTestsPage,
  autoperf: AutoPerfPage,
  'live-test': LiveTestPage,
};
