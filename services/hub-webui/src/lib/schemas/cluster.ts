import { z } from 'zod';

export const clusterRegisterSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  region: z.string().min(1, 'Region is required'),
  datacenter: z.string().min(1, 'Datacenter is required'),
  headend_url: z.string().url('Must be a valid URL'),
});

export const clusterUpdateSchema = z.object({
  name: z.string().min(1).optional(),
  region: z.string().min(1).optional(),
  datacenter: z.string().min(1).optional(),
  status: z.enum(['active', 'inactive', 'maintenance']).optional(),
});

export type ClusterRegisterInput = z.infer<typeof clusterRegisterSchema>;
export type ClusterUpdateInput = z.infer<typeof clusterUpdateSchema>;
