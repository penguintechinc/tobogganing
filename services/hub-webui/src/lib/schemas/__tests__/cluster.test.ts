import { describe, it, expect } from 'vitest';
import {
  clusterRegisterSchema,
  clusterUpdateSchema,
  type ClusterRegisterInput,
  type ClusterUpdateInput,
} from '../cluster';

describe('clusterRegisterSchema', () => {
  describe('valid cluster registration', () => {
    it('should pass with all required fields', () => {
      const input = {
        name: 'production-cluster',
        region: 'us-east-1',
        datacenter: 'us-east-1a',
        headend_url: 'https://headend.example.com',
      };
      const result = clusterRegisterSchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data).toEqual(input);
      }
    });

    it('should accept various valid URLs', () => {
      const urls = [
        'https://headend.example.com',
        'https://192.168.1.1:8443',
        'https://api.internal.local',
        'http://localhost:3000',
      ];
      urls.forEach((url) => {
        const input = {
          name: 'test-cluster',
          region: 'us-west-2',
          datacenter: 'us-west-2b',
          headend_url: url,
        };
        const result = clusterRegisterSchema.safeParse(input);
        expect(result.success).toBe(true);
      });
    });

    it('should accept different region formats', () => {
      const regions = ['us-east-1', 'eu-west-1', 'ap-southeast-1', 'local'];
      regions.forEach((region) => {
        const input = {
          name: 'test-cluster',
          region,
          datacenter: 'dc1',
          headend_url: 'https://headend.example.com',
        };
        const result = clusterRegisterSchema.safeParse(input);
        expect(result.success).toBe(true);
      });
    });

    it('should accept different datacenter formats', () => {
      const datacenters = ['us-east-1a', 'zone-1', 'dc-primary', 'on-prem-dc'];
      datacenters.forEach((dc) => {
        const input = {
          name: 'test-cluster',
          region: 'us-east-1',
          datacenter: dc,
          headend_url: 'https://headend.example.com',
        };
        const result = clusterRegisterSchema.safeParse(input);
        expect(result.success).toBe(true);
      });
    });
  });

  describe('required field validation', () => {
    it('should fail when name is missing', () => {
      const input = {
        region: 'us-east-1',
        datacenter: 'us-east-1a',
        headend_url: 'https://headend.example.com',
      };
      const result = clusterRegisterSchema.safeParse(input);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.flatten().fieldErrors.name).toBeDefined();
      }
    });

    it('should fail when name is empty string', () => {
      const input = {
        name: '',
        region: 'us-east-1',
        datacenter: 'us-east-1a',
        headend_url: 'https://headend.example.com',
      };
      const result = clusterRegisterSchema.safeParse(input);
      expect(result.success).toBe(false);
    });

    it('should fail when region is missing', () => {
      const input = {
        name: 'production-cluster',
        datacenter: 'us-east-1a',
        headend_url: 'https://headend.example.com',
      };
      const result = clusterRegisterSchema.safeParse(input);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.flatten().fieldErrors.region).toBeDefined();
      }
    });

    it('should fail when region is empty string', () => {
      const input = {
        name: 'production-cluster',
        region: '',
        datacenter: 'us-east-1a',
        headend_url: 'https://headend.example.com',
      };
      const result = clusterRegisterSchema.safeParse(input);
      expect(result.success).toBe(false);
    });

    it('should fail when datacenter is missing', () => {
      const input = {
        name: 'production-cluster',
        region: 'us-east-1',
        headend_url: 'https://headend.example.com',
      };
      const result = clusterRegisterSchema.safeParse(input);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.flatten().fieldErrors.datacenter).toBeDefined();
      }
    });

    it('should fail when datacenter is empty string', () => {
      const input = {
        name: 'production-cluster',
        region: 'us-east-1',
        datacenter: '',
        headend_url: 'https://headend.example.com',
      };
      const result = clusterRegisterSchema.safeParse(input);
      expect(result.success).toBe(false);
    });

    it('should fail when headend_url is missing', () => {
      const input = {
        name: 'production-cluster',
        region: 'us-east-1',
        datacenter: 'us-east-1a',
      };
      const result = clusterRegisterSchema.safeParse(input);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.flatten().fieldErrors.headend_url).toBeDefined();
      }
    });
  });

  describe('URL validation', () => {
    it('should reject invalid URL format', () => {
      const input = {
        name: 'production-cluster',
        region: 'us-east-1',
        datacenter: 'us-east-1a',
        headend_url: 'not-a-url',
      };
      const result = clusterRegisterSchema.safeParse(input);
      expect(result.success).toBe(false);
    });

    it('should reject URL without protocol', () => {
      const input = {
        name: 'production-cluster',
        region: 'us-east-1',
        datacenter: 'us-east-1a',
        headend_url: 'headend.example.com',
      };
      const result = clusterRegisterSchema.safeParse(input);
      expect(result.success).toBe(false);
    });

    it('should reject empty URL string', () => {
      const input = {
        name: 'production-cluster',
        region: 'us-east-1',
        datacenter: 'us-east-1a',
        headend_url: '',
      };
      const result = clusterRegisterSchema.safeParse(input);
      expect(result.success).toBe(false);
    });

    it('should accept URLs with paths', () => {
      const input = {
        name: 'production-cluster',
        region: 'us-east-1',
        datacenter: 'us-east-1a',
        headend_url: 'https://headend.example.com/api/v1',
      };
      const result = clusterRegisterSchema.safeParse(input);
      expect(result.success).toBe(true);
    });

    it('should accept URLs with query parameters', () => {
      const input = {
        name: 'production-cluster',
        region: 'us-east-1',
        datacenter: 'us-east-1a',
        headend_url: 'https://headend.example.com?param=value',
      };
      const result = clusterRegisterSchema.safeParse(input);
      expect(result.success).toBe(true);
    });
  });
});

describe('clusterUpdateSchema', () => {
  describe('partial updates', () => {
    it('should accept update with only name', () => {
      const input = { name: 'updated-cluster' };
      const result = clusterUpdateSchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data.name).toBe('updated-cluster');
      }
    });

    it('should accept update with only region', () => {
      const input = { region: 'eu-west-1' };
      const result = clusterUpdateSchema.safeParse(input);
      expect(result.success).toBe(true);
    });

    it('should accept update with only datacenter', () => {
      const input = { datacenter: 'eu-west-1b' };
      const result = clusterUpdateSchema.safeParse(input);
      expect(result.success).toBe(true);
    });

    it('should accept update with only status', () => {
      const input = { status: 'maintenance' };
      const result = clusterUpdateSchema.safeParse(input);
      expect(result.success).toBe(true);
    });

    it('should accept update with multiple fields', () => {
      const input = {
        name: 'updated-cluster',
        region: 'eu-west-1',
        status: 'inactive',
      };
      const result = clusterUpdateSchema.safeParse(input);
      expect(result.success).toBe(true);
      if (result.success) {
        expect(result.data).toEqual(input);
      }
    });

    it('should accept all valid status values', () => {
      const statuses = ['active', 'inactive', 'maintenance'];
      statuses.forEach((status) => {
        const input = { status };
        const result = clusterUpdateSchema.safeParse(input);
        expect(result.success).toBe(true);
      });
    });

    it('should accept empty object', () => {
      const input = {};
      const result = clusterUpdateSchema.safeParse(input);
      expect(result.success).toBe(true);
    });
  });

  describe('field constraints in partial updates', () => {
    it('should reject name with empty string', () => {
      const input = { name: '' };
      const result = clusterUpdateSchema.safeParse(input);
      expect(result.success).toBe(false);
    });

    it('should reject region with empty string', () => {
      const input = { region: '' };
      const result = clusterUpdateSchema.safeParse(input);
      expect(result.success).toBe(false);
    });

    it('should reject datacenter with empty string', () => {
      const input = { datacenter: '' };
      const result = clusterUpdateSchema.safeParse(input);
      expect(result.success).toBe(false);
    });

    it('should reject invalid status value', () => {
      const input = { status: 'invalid_status' };
      const result = clusterUpdateSchema.safeParse(input);
      expect(result.success).toBe(false);
      if (!result.success) {
        expect(result.error.flatten().fieldErrors.status).toBeDefined();
      }
    });
  });

  describe('comprehensive update scenarios', () => {
    it('should allow updating all fields simultaneously', () => {
      const input = {
        name: 'prod-cluster-v2',
        region: 'us-west-2',
        datacenter: 'us-west-2a',
        status: 'active',
      };
      const result = clusterUpdateSchema.safeParse(input);
      expect(result.success).toBe(true);
    });

    it('should handle status transition from active to maintenance', () => {
      const input = { status: 'maintenance' };
      const result = clusterUpdateSchema.safeParse(input);
      expect(result.success).toBe(true);
    });

    it('should handle status transition from maintenance to active', () => {
      const input = { status: 'active' };
      const result = clusterUpdateSchema.safeParse(input);
      expect(result.success).toBe(true);
    });
  });
});
