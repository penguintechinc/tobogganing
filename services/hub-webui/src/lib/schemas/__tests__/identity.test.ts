import { describe, it, expect } from 'vitest';
import {
  tenantCreateSchema,
  teamCreateSchema,
  spiffeEntrySchema,
  type TenantCreateInput,
  type TeamCreateInput,
  type SpiffeEntryInput,
} from '../identity';

describe('tenantCreateSchema', () => {
  describe('valid tenant creation', () => {
    it('should pass with minimal required fields', () => {
      const input = {
        tenant_id: 'tenant-001',
        name: 'ACME Corporation',
      };
      const result = tenantCreateSchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.tenant_id).toBe('tenant-001');
        expect(result.data.name).toBe('ACME Corporation');
      }
    });

    it('should pass with all fields populated', () => {
      const input = {
        tenant_id: 'tenant-001',
        name: 'ACME Corporation',
        domain: 'acme.com',
        spiffe_trust_domain: 'acme.io',
        config: {
          billing_email: 'billing@acme.com',
          max_users: 1000,
          features: ['advanced_auth', 'sso'],
        },
      };
      const result = tenantCreateSchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data).toEqual(input);
        expect(result.data.config.billing_email).toBe('billing@acme.com');
      }
    });

    it('should accept various tenant_id formats', () => {
      const validIds = [
        'tenant-001',
        'acme-corp',
        'tenant_123',
        'org-uuid-1234-5678',
      ];
      validIds.forEach((id) => {
        const input = {
          tenant_id: id,
          name: 'Test Tenant',
        };
        const result = tenantCreateSchema.safeParse(input);
        expect(result.success).toBe(true);
      });
    });

    it('should accept various domain formats', () => {
      const domains = [
        'example.com',
        'subdomain.example.com',
        'example.co.uk',
        'internal.local',
      ];
      domains.forEach((domain) => {
        const input = {
          tenant_id: 'tenant-001',
          name: 'Test',
          domain,
        };
        const result = tenantCreateSchema.safeParse(input);
        expect(result.success).toBe(true);
      });
    });

    it('should accept SPIFFE trust domains', () => {
      const domains = [
        'example.io',
        'internal.acme.com',
        'spiffe.local',
      ];
      domains.forEach((domain) => {
        const input = {
          tenant_id: 'tenant-001',
          name: 'Test',
          spiffe_trust_domain: domain,
        };
        const result = tenantCreateSchema.safeParse(input);
        expect(result.success).toBe(true);
      });
    });

    it('should accept arbitrary config objects', () => {
      const configs = [
        { key1: 'value1' },
        { nested: { deep: { value: 123 } } },
        { array: [1, 2, 3], string: 'test', boolean: true },
        {},
      ];
      configs.forEach((config) => {
        const input = {
          tenant_id: 'tenant-001',
          name: 'Test',
          config,
        };
        const result = tenantCreateSchema.safeParse(input);
        expect(result.success).toBe(true);
      });
    });
  });

  describe('required field validation', () => {
    it('should fail when tenant_id is missing', () => {
      const input = {
        name: 'Test Tenant',
      };
      const result = tenantCreateSchema.safeParse(input);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.flatten().fieldErrors.tenant_id).toBeDefined();
      }
    });

    it('should fail when tenant_id is empty string', () => {
      const input = {
        tenant_id: '',
        name: 'Test Tenant',
      };
      const result = tenantCreateSchema.safeParse(input);
      expect(result.success).toBe(false);
    });

    it('should fail when name is missing', () => {
      const input = {
        tenant_id: 'tenant-001',
      };
      const result = tenantCreateSchema.safeParse(input);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.flatten().fieldErrors.name).toBeDefined();
      }
    });

    it('should fail when name is empty string', () => {
      const input = {
        tenant_id: 'tenant-001',
        name: '',
      };
      const result = tenantCreateSchema.safeParse(input);
      expect(result.success).toBe(false);
    });
  });

  describe('optional fields', () => {
    it('should handle missing optional fields', () => {
      const input = {
        tenant_id: 'tenant-001',
        name: 'Test Tenant',
      };
      const result = tenantCreateSchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.domain).toBeUndefined();
        expect(result.data.spiffe_trust_domain).toBeUndefined();
        expect(result.data.config).toBeUndefined();
      }
    });
  });
});

describe('teamCreateSchema', () => {
  describe('valid team creation', () => {
    it('should pass with minimal required fields', () => {
      const input = {
        team_id: 'team-001',
        tenant_id: 'tenant-001',
        name: 'Engineering',
      };
      const result = teamCreateSchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.team_id).toBe('team-001');
        expect(result.data.tenant_id).toBe('tenant-001');
        expect(result.data.name).toBe('Engineering');
      }
    });

    it('should pass with all fields populated', () => {
      const input = {
        team_id: 'team-001',
        tenant_id: 'tenant-001',
        name: 'Engineering',
        description: 'All software engineers and platform team members',
      };
      const result = teamCreateSchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data).toEqual(input);
      }
    });

    it('should accept various team_id formats', () => {
      const validIds = [
        'team-001',
        'engineering',
        'team_uuid_123',
        'product-dev',
      ];
      validIds.forEach((id) => {
        const input = {
          team_id: id,
          tenant_id: 'tenant-001',
          name: 'Team',
        };
        const result = teamCreateSchema.safeParse(input);
        expect(result.success).toBe(true);
      });
    });

    it('should accept various team names', () => {
      const names = [
        'Engineering',
        'Sales & Marketing',
        'DevOps/Infrastructure',
        'Security',
      ];
      names.forEach((name) => {
        const input = {
          team_id: 'team-001',
          tenant_id: 'tenant-001',
          name,
        };
        const result = teamCreateSchema.safeParse(input);
        expect(result.success).toBe(true);
      });
    });
  });

  describe('required field validation', () => {
    it('should fail when team_id is missing', () => {
      const input = {
        tenant_id: 'tenant-001',
        name: 'Engineering',
      };
      const result = teamCreateSchema.safeParse(input);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.flatten().fieldErrors.team_id).toBeDefined();
      }
    });

    it('should fail when team_id is empty string', () => {
      const input = {
        team_id: '',
        tenant_id: 'tenant-001',
        name: 'Engineering',
      };
      const result = teamCreateSchema.safeParse(input);
      expect(result.success).toBe(false);
    });

    it('should fail when tenant_id is missing', () => {
      const input = {
        team_id: 'team-001',
        name: 'Engineering',
      };
      const result = teamCreateSchema.safeParse(input);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.flatten().fieldErrors.tenant_id).toBeDefined();
      }
    });

    it('should fail when tenant_id is empty string', () => {
      const input = {
        team_id: 'team-001',
        tenant_id: '',
        name: 'Engineering',
      };
      const result = teamCreateSchema.safeParse(input);
      expect(result.success).toBe(false);
    });

    it('should fail when name is missing', () => {
      const input = {
        team_id: 'team-001',
        tenant_id: 'tenant-001',
      };
      const result = teamCreateSchema.safeParse(input);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.flatten().fieldErrors.name).toBeDefined();
      }
    });

    it('should fail when name is empty string', () => {
      const input = {
        team_id: 'team-001',
        tenant_id: 'tenant-001',
        name: '',
      };
      const result = teamCreateSchema.safeParse(input);
      expect(result.success).toBe(false);
    });
  });

  describe('optional fields', () => {
    it('should handle missing description', () => {
      const input = {
        team_id: 'team-001',
        tenant_id: 'tenant-001',
        name: 'Engineering',
      };
      const result = teamCreateSchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.description).toBeUndefined();
      }
    });
  });
});

describe('spiffeEntrySchema', () => {
  describe('valid SPIFFE entry creation', () => {
    it('should pass with minimal required fields', () => {
      const input = {
        spiffe_id: 'spiffe://example.io/service/api',
        tenant_id: 'tenant-001',
      };
      const result = spiffeEntrySchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.spiffe_id).toBe('spiffe://example.io/service/api');
        expect(result.data.tenant_id).toBe('tenant-001');
        expect(result.data.ttl).toBe(0);
      }
    });

    it('should pass with all fields populated', () => {
      const input = {
        spiffe_id: 'spiffe://example.io/service/api',
        tenant_id: 'tenant-001',
        parent_id: 'spiffe://example.io/agent/node1',
        selectors: {
          'k8s:pod-name': 'api-server',
          'k8s:namespace': 'default',
        },
        ttl: 3600,
        dns_names: ['api.example.com', 'api-internal.example.com'],
      };
      const result = spiffeEntrySchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data).toEqual(input);
      }
    });

    it('should accept various valid SPIFFE IDs', () => {
      const validIds = [
        'spiffe://example.io/service/api',
        'spiffe://internal.acme.com/service/db',
        'spiffe://trust.domain/workload/nginx',
        'spiffe://spiffe.local/service/frontend',
      ];
      validIds.forEach((id) => {
        const input = {
          spiffe_id: id,
          tenant_id: 'tenant-001',
        };
        const result = spiffeEntrySchema.safeParse(input);
        expect(result.success).toBe(true);
      });
    });

    it('should accept arbitrary selector objects', () => {
      const selectors = [
        { 'k8s:pod-name': 'api-1', 'k8s:namespace': 'default' },
        { 'docker:container-id': 'abc123' },
        { 'vm:hostname': 'node1', 'vm:region': 'us-east-1' },
        {},
      ];
      selectors.forEach((selector) => {
        const input = {
          spiffe_id: 'spiffe://example.io/service/api',
          tenant_id: 'tenant-001',
          selectors: selector,
        };
        const result = spiffeEntrySchema.safeParse(input);
        expect(result.success).toBe(true);
      });
    });

    it('should accept various TTL values', () => {
      const ttls = [0, 1, 3600, 86400, 604800, Number.MAX_SAFE_INTEGER];
      ttls.forEach((ttl) => {
        const input = {
          spiffe_id: 'spiffe://example.io/service/api',
          tenant_id: 'tenant-001',
          ttl,
        };
        const result = spiffeEntrySchema.safeParse(input);
        expect(result.success).toBe(true);
      });
    });

    it('should accept multiple DNS names', () => {
      const input = {
        spiffe_id: 'spiffe://example.io/service/api',
        tenant_id: 'tenant-001',
        dns_names: [
          'api.example.com',
          'api-internal.example.com',
          'api.prod.internal',
        ],
      };
      const result = spiffeEntrySchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.dns_names).toHaveLength(3);
      }
    });
  });

  describe('required field validation', () => {
    it('should fail when spiffe_id is missing', () => {
      const input = {
        tenant_id: 'tenant-001',
      };
      const result = spiffeEntrySchema.safeParse(input);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.flatten().fieldErrors.spiffe_id).toBeDefined();
      }
    });

    it('should fail when spiffe_id is empty string', () => {
      const input = {
        spiffe_id: '',
        tenant_id: 'tenant-001',
      };
      const result = spiffeEntrySchema.safeParse(input);
      expect(result.success).toBe(false);
    });

    it('should fail when tenant_id is missing', () => {
      const input = {
        spiffe_id: 'spiffe://example.io/service/api',
      };
      const result = spiffeEntrySchema.safeParse(input);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.flatten().fieldErrors.tenant_id).toBeDefined();
      }
    });

    it('should fail when tenant_id is empty string', () => {
      const input = {
        spiffe_id: 'spiffe://example.io/service/api',
        tenant_id: '',
      };
      const result = spiffeEntrySchema.safeParse(input);
      expect(result.success).toBe(false);
    });
  });

  describe('SPIFFE ID format validation', () => {
    it('should reject SPIFFE IDs not starting with spiffe://', () => {
      const invalidIds = [
        'https://example.io/service/api',
        'example.io/service/api',
        'service/api',
        'spiffe:/example.io/service/api',
      ];
      invalidIds.forEach((id) => {
        const input = {
          spiffe_id: id,
          tenant_id: 'tenant-001',
        };
        const result = spiffeEntrySchema.safeParse(input);
        expect(result.success).toBe(false);
        if (!result.success) {
          expect(result.error.flatten().fieldErrors.spiffe_id).toBeDefined();
        }
      });
    });

    it('should enforce spiffe:// prefix', () => {
      const input = {
        spiffe_id: 'spiffe://example.io/service/api',
        tenant_id: 'tenant-001',
      };
      const result = spiffeEntrySchema.safeParse(input);
      expect(result.success).toBe(true);
    });
  });

  describe('TTL validation', () => {
    it('should reject negative TTL', () => {
      const input = {
        spiffe_id: 'spiffe://example.io/service/api',
        tenant_id: 'tenant-001',
        ttl: -1,
      };
      const result = spiffeEntrySchema.safeParse(input);
      expect(result.success).toBe(false);
    });

    it('should reject non-integer TTL', () => {
      const input = {
        spiffe_id: 'spiffe://example.io/service/api',
        tenant_id: 'tenant-001',
        ttl: 3600.5,
      };
      const result = spiffeEntrySchema.safeParse(input);
      expect(result.success).toBe(false);
    });

    it('should default TTL to 0', () => {
      const input = {
        spiffe_id: 'spiffe://example.io/service/api',
        tenant_id: 'tenant-001',
      };
      const result = spiffeEntrySchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.ttl).toBe(0);
      }
    });
  });

  describe('optional fields', () => {
    it('should handle missing parent_id', () => {
      const input = {
        spiffe_id: 'spiffe://example.io/service/api',
        tenant_id: 'tenant-001',
      };
      const result = spiffeEntrySchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.parent_id).toBeUndefined();
      }
    });

    it('should handle missing selectors', () => {
      const input = {
        spiffe_id: 'spiffe://example.io/service/api',
        tenant_id: 'tenant-001',
      };
      const result = spiffeEntrySchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.selectors).toBeUndefined();
      }
    });

    it('should handle missing dns_names', () => {
      const input = {
        spiffe_id: 'spiffe://example.io/service/api',
        tenant_id: 'tenant-001',
      };
      const result = spiffeEntrySchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.dns_names).toBeUndefined();
      }
    });

    it('should handle empty dns_names array', () => {
      const input = {
        spiffe_id: 'spiffe://example.io/service/api',
        tenant_id: 'tenant-001',
        dns_names: [],
      };
      const result = spiffeEntrySchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.dns_names).toEqual([]);
      }
    });
  });
});
