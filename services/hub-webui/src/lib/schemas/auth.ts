import { z } from 'zod';

export const loginSchema = z.object({
  username: z.string().min(1, 'Username is required'),
  password: z.string().min(1, 'Password is required'),
});

export const tokenRequestSchema = z.object({
  node_id: z.string().min(1),
  node_type: z.enum(['kubernetes_node', 'raw_compute', 'client_docker', 'client_native']),
  api_key: z.string().min(1),
});

export type LoginInput = z.infer<typeof loginSchema>;
export type TokenRequestInput = z.infer<typeof tokenRequestSchema>;
