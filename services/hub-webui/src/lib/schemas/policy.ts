import { z } from 'zod';

const cidrPattern = /^(\d{1,3}\.){3}\d{1,3}\/\d{1,2}$|^[0-9a-fA-F:]+\/\d{1,3}$/;
const portRangePattern = /^\d{1,5}(-\d{1,5})?$/;

export const policyRuleCreateSchema = z.object({
  name: z.string().min(1, 'Name is required'),
  description: z.string().optional(),
  action: z.enum(['allow', 'deny']).default('allow'),
  priority: z.number().int().min(0).max(65535).default(100),
  scope: z.enum(['wireguard', 'k8s', 'openziti', 'both']).default('both'),
  direction: z.enum(['inbound', 'outbound', 'both']).default('both'),
  domains: z.array(z.string()).optional(),
  ports: z.array(z.string().regex(portRangePattern, 'Invalid port or port range')).optional(),
  protocol: z.enum(['tcp', 'udp', 'icmp', 'any']).default('any'),
  src_cidrs: z.array(z.string().regex(cidrPattern, 'Invalid CIDR notation')).optional(),
  dst_cidrs: z.array(z.string().regex(cidrPattern, 'Invalid CIDR notation')).optional(),
  users: z.array(z.string()).optional(),
  groups: z.array(z.string()).optional(),
  identity_provider: z.enum(['local', 'oidc', 'saml', 'scim']).default('local'),
  enabled: z.boolean().default(true),
  tenant_id: z.string().optional(),
});

export const policyRuleUpdateSchema = policyRuleCreateSchema.partial();

export type PolicyRuleCreateInput = z.infer<typeof policyRuleCreateSchema>;
export type PolicyRuleUpdateInput = z.infer<typeof policyRuleUpdateSchema>;
