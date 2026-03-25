import { describe, it, expect } from 'vitest';
import {
  policyRuleCreateSchema,
  policyRuleUpdateSchema,
  type PolicyRuleCreateInput,
  type PolicyRuleUpdateInput,
} from '../policy';

describe('policyRuleCreateSchema', () => {
  describe('valid policy rule creation', () => {
    it('should pass with minimal required fields', () => {
      const input = {
        name: 'Allow HTTP',
      };
      const result = policyRuleCreateSchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.name).toBe('Allow HTTP');
        expect(result.data.action).toBe('allow');
        expect(result.data.protocol).toBe('any');
        expect(result.data.scope).toBe('both');
        expect(result.data.direction).toBe('both');
      }
    });

    it('should pass with all fields populated', () => {
      const input = {
        name: 'Secure policy',
        description: 'A comprehensive security rule',
        action: 'deny',
        priority: 500,
        scope: 'wireguard',
        direction: 'inbound',
        domains: ['example.com', 'api.example.com'],
        ports: ['80', '443', '8000-8999'],
        protocol: 'tcp',
        src_cidrs: ['192.168.0.0/16', '10.0.0.0/8'],
        dst_cidrs: ['172.16.0.0/12'],
        users: ['alice@example.com', 'bob@example.com'],
        groups: ['admins', 'developers'],
        identity_provider: 'oidc',
        enabled: false,
        tenant_id: 'tenant-123',
      };
      const result = policyRuleCreateSchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data).toEqual(input);
      }
    });

    it('should accept all valid scope values', () => {
      const scopes = ['wireguard', 'k8s', 'openziti', 'both'];
      scopes.forEach((scope) => {
        const input = { name: 'Test rule', scope };
        const result = policyRuleCreateSchema.safeParse(input);
        expect(result.success).toBe(true);
      });
    });

    it('should accept all valid direction values', () => {
      const directions = ['inbound', 'outbound', 'both'];
      directions.forEach((direction) => {
        const input = { name: 'Test rule', direction };
        const result = policyRuleCreateSchema.safeParse(input);
        expect(result.success).toBe(true);
      });
    });

    it('should accept all valid action values', () => {
      const actions = ['allow', 'deny'];
      actions.forEach((action) => {
        const input = { name: 'Test rule', action };
        const result = policyRuleCreateSchema.safeParse(input);
        expect(result.success).toBe(true);
      });
    });

    it('should accept all valid protocol values', () => {
      const protocols = ['tcp', 'udp', 'icmp', 'any'];
      protocols.forEach((protocol) => {
        const input = { name: 'Test rule', protocol };
        const result = policyRuleCreateSchema.safeParse(input);
        expect(result.success).toBe(true);
      });
    });

    it('should accept all valid identity providers', () => {
      const providers = ['local', 'oidc', 'saml', 'scim'];
      providers.forEach((provider) => {
        const input = { name: 'Test rule', identity_provider: provider };
        const result = policyRuleCreateSchema.safeParse(input);
        expect(result.success).toBe(true);
      });
    });
  });

  describe('required field validation', () => {
    it('should fail when name is missing', () => {
      const input = {
        description: 'Missing name',
      };
      const result = policyRuleCreateSchema.safeParse(input);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.flatten().fieldErrors.name).toBeDefined();
      }
    });

    it('should fail when name is empty string', () => {
      const input = { name: '' };
      const result = policyRuleCreateSchema.safeParse(input);
      expect(result.success).toBe(false);
    });
  });

  describe('CIDR validation', () => {
    it('should accept valid IPv4 CIDR notation', () => {
      const validCIDRs = [
        '192.168.0.0/16',
        '10.0.0.0/8',
        '172.16.0.0/12',
        '0.0.0.0/0',
        '255.255.255.255/32',
      ];
      validCIDRs.forEach((cidr) => {
        const input = { name: 'Test', src_cidrs: [cidr] };
        const result = policyRuleCreateSchema.safeParse(input);
        expect(result.success).toBe(true);
      });
    });

    it('should accept valid IPv6 CIDR notation', () => {
      const validCIDRs = [
        '2001:db8::/32',
        'fe80::/10',
        '::/0',
        '::1/128',
      ];
      validCIDRs.forEach((cidr) => {
        const input = { name: 'Test', dst_cidrs: [cidr] };
        const result = policyRuleCreateSchema.safeParse(input);
        expect(result.success).toBe(true);
      });
    });

    it('should reject invalid CIDR notation in src_cidrs', () => {
      const input = {
        name: 'Test',
        src_cidrs: ['192.168.1.1'],
      };
      const result = policyRuleCreateSchema.safeParse(input);
      expect(result.success).toBe(false);
    });

    it('should reject invalid CIDR notation in dst_cidrs', () => {
      const input = {
        name: 'Test',
        dst_cidrs: ['invalid-cidr'],
      };
      const result = policyRuleCreateSchema.safeParse(input);
      expect(result.success).toBe(false);
    });

    it('should reject CIDR with wrong subnet mask', () => {
      const input = {
        name: 'Test',
        src_cidrs: ['192.168.0.0/33'],
      };
      const result = policyRuleCreateSchema.safeParse(input);
      expect(result.success).toBe(false);
    });
  });

  describe('protocol validation', () => {
    it('should reject invalid protocol', () => {
      const input = {
        name: 'Test',
        protocol: 'http',
      };
      const result = policyRuleCreateSchema.safeParse(input);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.flatten().fieldErrors.protocol).toBeDefined();
      }
    });

    it('should reject protocol as string type mismatch', () => {
      const input = {
        name: 'Test',
        protocol: 123,
      };
      const result = policyRuleCreateSchema.safeParse(input);
      expect(result.success).toBe(false);
    });
  });

  describe('port range validation', () => {
    it('should accept single port', () => {
      const input = { name: 'Test', ports: ['80'] };
      const result = policyRuleCreateSchema.safeParse(input);
      expect(result.success).toBe(true);
    });

    it('should accept port ranges', () => {
      const input = { name: 'Test', ports: ['8000-8999', '1000-2000'] };
      const result = policyRuleCreateSchema.safeParse(input);
      expect(result.success).toBe(true);
    });

    it('should accept mixed single ports and ranges', () => {
      const input = { name: 'Test', ports: ['80', '443', '8000-8999'] };
      const result = policyRuleCreateSchema.safeParse(input);
      expect(result.success).toBe(true);
    });

    it('should reject invalid port format', () => {
      const input = { name: 'Test', ports: ['invalid'] };
      const result = policyRuleCreateSchema.safeParse(input);
      expect(result.success).toBe(false);
    });

    it('should reject port with invalid range syntax', () => {
      const input = { name: 'Test', ports: ['80-'] };
      const result = policyRuleCreateSchema.safeParse(input);
      expect(result.success).toBe(false);
    });

    it('should reject port with extra hyphens', () => {
      const input = { name: 'Test', ports: ['80-90-100'] };
      const result = policyRuleCreateSchema.safeParse(input);
      expect(result.success).toBe(false);
    });
  });

  describe('priority validation', () => {
    it('should accept priority within valid range', () => {
      const input = { name: 'Test', priority: 100 };
      const result = policyRuleCreateSchema.safeParse(input);
      expect(result.success).toBe(true);
    });

    it('should accept minimum priority (0)', () => {
      const input = { name: 'Test', priority: 0 };
      const result = policyRuleCreateSchema.safeParse(input);
      expect(result.success).toBe(true);
    });

    it('should accept maximum priority (65535)', () => {
      const input = { name: 'Test', priority: 65535 };
      const result = policyRuleCreateSchema.safeParse(input);
      expect(result.success).toBe(true);
    });

    it('should reject priority below minimum', () => {
      const input = { name: 'Test', priority: -1 };
      const result = policyRuleCreateSchema.safeParse(input);
      expect(result.success).toBe(false);
    });

    it('should reject priority above maximum', () => {
      const input = { name: 'Test', priority: 65536 };
      const result = policyRuleCreateSchema.safeParse(input);
      expect(result.success).toBe(false);
    });

    it('should reject non-integer priority', () => {
      const input = { name: 'Test', priority: 100.5 };
      const result = policyRuleCreateSchema.safeParse(input);
      expect(result.success).toBe(false);
    });
  });

  describe('scope validation', () => {
    it('should reject invalid scope value', () => {
      const input = {
        name: 'Test',
        scope: 'invalid_scope',
      };
      const result = policyRuleCreateSchema.safeParse(input);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.flatten().fieldErrors.scope).toBeDefined();
      }
    });
  });

  describe('array handling', () => {
    it('should handle empty arrays correctly', () => {
      const input = {
        name: 'Test',
        domains: [],
        ports: [],
        src_cidrs: [],
        dst_cidrs: [],
        users: [],
        groups: [],
      };
      const result = policyRuleCreateSchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.domains).toEqual([]);
        expect(result.data.ports).toEqual([]);
      }
    });

    it('should handle optional arrays when omitted', () => {
      const input = { name: 'Test' };
      const result = policyRuleCreateSchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.domains).toBeUndefined();
        expect(result.data.ports).toBeUndefined();
      }
    });
  });

  describe('enabled field', () => {
    it('should default to true', () => {
      const input = { name: 'Test' };
      const result = policyRuleCreateSchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.enabled).toBe(true);
      }
    });

    it('should accept false', () => {
      const input = { name: 'Test', enabled: false };
      const result = policyRuleCreateSchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.enabled).toBe(false);
      }
    });
  });
});

describe('policyRuleUpdateSchema', () => {
  it('should accept partial update with only name', () => {
    const input = { name: 'Updated name' };
    const result = policyRuleUpdateSchema.safeParse(input);
    expect(result.success).toBe(true);
  });

  it('should accept partial update with multiple fields', () => {
    const input = {
      priority: 200,
      enabled: false,
      description: 'Updated description',
    };
    const result = policyRuleUpdateSchema.safeParse(input);
    expect(result.success).toBe(true);
  });

  it('should accept empty object', () => {
    const input = {};
    const result = policyRuleUpdateSchema.safeParse(input);
    expect(result.success).toBe(true);
  });

  it('should validate fields against original constraints', () => {
    const input = {
      protocol: 'invalid_protocol',
    };
    const result = policyRuleUpdateSchema.safeParse(input);
    expect(result.success).toBe(false);
  });
});
