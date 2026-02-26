import { z } from 'zod';

export const tenantCreateSchema = z.object({
  tenant_id: z.string().min(1, 'Tenant ID is required'),
  name: z.string().min(1, 'Name is required'),
  domain: z.string().optional(),
  spiffe_trust_domain: z.string().optional(),
  config: z.record(z.unknown()).optional(),
});

export const teamCreateSchema = z.object({
  team_id: z.string().min(1, 'Team ID is required'),
  tenant_id: z.string().min(1, 'Tenant ID is required'),
  name: z.string().min(1, 'Name is required'),
  description: z.string().optional(),
});

export const spiffeEntrySchema = z.object({
  spiffe_id: z.string().min(1, 'SPIFFE ID is required').regex(/^spiffe:\/\//, 'Must start with spiffe://'),
  tenant_id: z.string().min(1, 'Tenant ID is required'),
  parent_id: z.string().optional(),
  selectors: z.record(z.unknown()).optional(),
  ttl: z.number().int().min(0).default(0),
  dns_names: z.array(z.string()).optional(),
});

export type TenantCreateInput = z.infer<typeof tenantCreateSchema>;
export type TeamCreateInput = z.infer<typeof teamCreateSchema>;
export type SpiffeEntryInput = z.infer<typeof spiffeEntrySchema>;
