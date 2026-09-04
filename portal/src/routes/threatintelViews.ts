import type { ComponentType } from 'react';
import { IocCheckPage } from '../pages/threatintel/IocCheckPage';
import { FeedsPage } from '../pages/threatintel/FeedsPage';
import { BlocklistPage } from '../pages/threatintel/BlocklistPage';

/**
 * View-slug -> page map for the threatintel module. Slugs derived from the
 * NavEntry labels registered in hub_api/modules/threatintel/__init__.py.
 */
export const threatintelViews: Record<string, ComponentType> = {
  feeds: FeedsPage,
  blocklist: BlocklistPage,
  'ioc-check': IocCheckPage,
};
