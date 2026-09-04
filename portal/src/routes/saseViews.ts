import type { ComponentType } from 'react';
import { ClustersPage } from '../pages/sase/ClustersPage';
import { ClientsPage } from '../pages/sase/ClientsPage';
import { StatusPage } from '../pages/sase/StatusPage';
import { BlockPageBuilder } from '../pages/sase/BlockPageBuilder';
import { BlockRoutingConfig } from '../pages/sase/BlockRoutingConfig';

/** View-slug -> page map for the sase module. Slugs derived from NavEntry labels. */
export const saseViews: Record<string, ComponentType> = {
  clusters: ClustersPage,
  clients: ClientsPage,
  status: StatusPage,
  'block-pages': BlockPageBuilder,
  'block-routing': BlockRoutingConfig,
};
