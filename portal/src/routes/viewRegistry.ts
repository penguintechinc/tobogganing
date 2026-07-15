import type { ComponentType } from 'react';
import { wpcViews } from './wpcViews';
import { c2cViews } from './c2cViews';
import { saseViews } from './saseViews';

/**
 * Central (module, view-slug) -> page component registry.
 * Each module contributes its own map from a dedicated file so view
 * work can proceed per-module without touching shared route code.
 */
const registry: Record<string, Record<string, ComponentType>> = {
  waddleperf_cluster: wpcViews,
  waddleperf_c2c: c2cViews,
  sase: saseViews,
};

export function resolveView(module: string, view: string): ComponentType | null {
  return registry[module]?.[view] ?? null;
}
