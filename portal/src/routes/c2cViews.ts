import type { ComponentType } from 'react';
import { EndpointsPage } from '../pages/c2c/EndpointsPage';
import { RunsPage } from '../pages/c2c/RunsPage';
import { RecurringPage } from '../pages/c2c/RecurringPage';
import { RegionsPage } from '../pages/c2c/RegionsPage';

/** View-slug -> page map for the waddleperf_c2c module. */
export const c2cViews: Record<string, ComponentType> = {
  'c2c-nodes': EndpointsPage,
  'c2c-runs': RunsPage,
  'c2c-matrix': RunsPage,
  'c2c-recurring': RecurringPage,
  'c2c-regions': RegionsPage,
};
