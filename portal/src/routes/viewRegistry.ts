import type { ComponentType } from 'react';
import { wpcViews } from './wpcViews';
import { c2cViews } from './c2cViews';
import { saseViews } from './saseViews';
import { netsvcsViews } from './netsvcsViews';
import { threatintelViews } from './threatintelViews';

/**
 * Central (module, view-slug) -> page component registry.
 * Each module contributes its own map from a dedicated file so view
 * work can proceed per-module without touching shared route code.
 */
const registry: Record<string, Record<string, ComponentType>> = {
  perftest_cluster: wpcViews,
  perftest_c2c: c2cViews,
  sase: saseViews,
  netsvcs: netsvcsViews,
  threatintel: threatintelViews,
};

export function resolveView(module: string, view: string): ComponentType | null {
  return registry[module]?.[view] ?? null;
}
