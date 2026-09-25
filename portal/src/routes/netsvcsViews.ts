import type { ComponentType } from 'react';
import { ZonesPage } from '../pages/netsvcs/ZonesPage';
import { DnsServersPage } from '../pages/netsvcs/DnsServersPage';
import { AnalyticsPage } from '../pages/netsvcs/AnalyticsPage';

/**
 * View-slug -> page map for the netsvcs module. Slugs derived from the
 * NavEntry labels registered in hub_api/modules/netsvcs/__init__.py.
 */
export const netsvcsViews: Record<string, ComponentType> = {
  zones: ZonesPage,
  'dns-servers': DnsServersPage,
  analytics: AnalyticsPage,
};
