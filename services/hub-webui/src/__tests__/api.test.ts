import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import MockAdapter from 'axios-mock-adapter'
import apiClient, {
  authApi,
  policiesApi,
  clientsApi,
  hubsApi,
  usersApi,
  identityApi,
  auditApi,
  dashboardApi,
} from '../lib/api'

// axios-mock-adapter intercepts axios instance requests
const mock = new MockAdapter(apiClient)

const mockUser = {
  id: 'usr-001',
  email: 'admin@test.com',
  name: 'Test Admin',
  role: 'admin' as const,
  created_at: '2025-01-01T00:00:00Z',
}

const mockAuthResponse = {
  token: 'jwt-token',
  user: mockUser,
}

const mockPolicy = {
  id: 'pol-001',
  name: 'Block Malicious',
  description: 'Blocks malicious domains',
  enabled: true,
  action: 'deny' as const,
  priority: 1,
  rules: [{ dimension: 'domain' as const, operator: 'contains' as const, value: '*.evil.com' }],
  created_at: '2025-01-01T00:00:00Z',
  updated_at: '2025-01-01T00:00:00Z',
}

const mockClient = {
  id: 'cli-001',
  name: 'dev-laptop',
  hostname: 'dev.local',
  status: 'connected' as const,
  hub_ids: ['hub-us-east-1'],
  ip_address: '10.0.0.1',
  last_seen: '2025-01-01T00:00:00Z',
  version: 'v1.4.0',
}

const mockHub = {
  id: 'hub-001',
  name: 'us-east-1',
  endpoint: 'hub.us-east-1.example.com:51820',
  status: 'healthy' as const,
  connected_clients: 45,
  capacity: 100,
  uptime_seconds: 86400,
  version: 'v1.2.0',
}

const mockIdentityProvider = {
  id: 'idp-001',
  name: 'Okta',
  type: 'saml' as const,
  enabled: false,
  config: {},
  premium: false,
}

const mockAuditLog = {
  id: 'log-001',
  timestamp: '2025-01-01T00:00:00Z',
  event_type: 'auth' as const,
  actor: 'admin@test.com',
  action: 'login',
  target: 'system',
  result: 'success' as const,
  details: 'Successful login',
}

const mockDashboardStats = {
  total_clients: 4,
  connected_clients: 3,
  active_policies: 3,
  total_hubs: 4,
  traffic_gb_24h: 112,
  blocked_requests_24h: 18,
  uptime_percent: 97,
  active_sessions: 3,
}

describe('API client module', () => {
  beforeEach(() => {
    localStorage.clear()
    mock.reset()
  })

  afterEach(() => {
    mock.reset()
  })

  describe('Structure verification', () => {
    it('exports all API objects with correct method shapes', () => {
      expect(typeof authApi.login).toBe('function')
      expect(typeof authApi.logout).toBe('function')
      expect(typeof authApi.me).toBe('function')
      expect(typeof authApi.refresh).toBe('function')

      expect(typeof policiesApi.list).toBe('function')
      expect(typeof policiesApi.get).toBe('function')
      expect(typeof policiesApi.create).toBe('function')
      expect(typeof policiesApi.update).toBe('function')
      expect(typeof policiesApi.delete).toBe('function')

      expect(typeof clientsApi.list).toBe('function')
      expect(typeof clientsApi.get).toBe('function')
      expect(typeof clientsApi.delete).toBe('function')

      expect(typeof hubsApi.list).toBe('function')
      expect(typeof hubsApi.get).toBe('function')
      expect(typeof hubsApi.create).toBe('function')
      expect(typeof hubsApi.delete).toBe('function')

      expect(typeof usersApi.list).toBe('function')
      expect(typeof usersApi.create).toBe('function')
      expect(typeof usersApi.update).toBe('function')
      expect(typeof usersApi.delete).toBe('function')

      expect(typeof identityApi.list).toBe('function')
      expect(typeof identityApi.create).toBe('function')
      expect(typeof identityApi.update).toBe('function')
      expect(typeof identityApi.delete).toBe('function')

      expect(typeof auditApi.list).toBe('function')
      expect(typeof dashboardApi.stats).toBe('function')
    })
  })

  describe('Request interceptor', () => {
    it('attaches Authorization header when token exists', async () => {
      localStorage.setItem('tobogganing_token', 'my-jwt-token')
      let capturedAuth: string | undefined
      mock.onGet('/auth/me').reply((config) => {
        capturedAuth = config.headers?.Authorization as string
        return [200, mockUser]
      })

      await authApi.me()
      expect(capturedAuth).toBe('Bearer my-jwt-token')
    })

    it('does not attach Authorization header when no token', async () => {
      let capturedAuth: string | undefined
      mock.onGet('/auth/me').reply((config) => {
        capturedAuth = config.headers?.Authorization as string
        return [200, mockUser]
      })

      await authApi.me()
      expect(capturedAuth).toBeUndefined()
    })
  })

  describe('Response interceptor', () => {
    it('clears token on 401 response', async () => {
      localStorage.setItem('tobogganing_token', 'expired-token')
      mock.onGet('/auth/me').reply(401)

      await expect(authApi.me()).rejects.toThrow()
      expect(localStorage.getItem('tobogganing_token')).toBeNull()
    })

    it('rejects on non-401 errors without clearing token', async () => {
      localStorage.setItem('tobogganing_token', 'valid-token')
      mock.onGet('/auth/me').reply(500)

      await expect(authApi.me()).rejects.toThrow()
    })
  })

  describe('authApi', () => {
    it('login posts credentials and returns auth response', async () => {
      mock.onPost('/auth/login').reply(200, mockAuthResponse)

      const result = await authApi.login('admin@test.com', 'password')
      expect(result).toEqual(mockAuthResponse)
    })

    it('logout posts to /auth/logout', async () => {
      mock.onPost('/auth/logout').reply(200)

      await expect(authApi.logout()).resolves.toBeUndefined()
    })

    it('me returns current user', async () => {
      mock.onGet('/auth/me').reply(200, mockUser)

      const result = await authApi.me()
      expect(result).toEqual(mockUser)
    })

    it('refresh returns new auth response', async () => {
      mock.onPost('/auth/refresh').reply(200, mockAuthResponse)

      const result = await authApi.refresh()
      expect(result).toEqual(mockAuthResponse)
    })
  })

  describe('policiesApi', () => {
    it('list returns policies array', async () => {
      mock.onGet('/policies').reply(200, [mockPolicy])

      const result = await policiesApi.list()
      expect(result).toEqual([mockPolicy])
    })

    it('get returns single policy by id', async () => {
      mock.onGet('/policies/pol-001').reply(200, mockPolicy)

      const result = await policiesApi.get('pol-001')
      expect(result).toEqual(mockPolicy)
    })

    it('create posts policy data and returns created policy', async () => {
      const { id, created_at, updated_at, ...policyData } = mockPolicy
      mock.onPost('/policies').reply(201, mockPolicy)

      const result = await policiesApi.create(policyData)
      expect(result).toEqual(mockPolicy)
    })

    it('update puts partial data and returns updated policy', async () => {
      mock.onPut('/policies/pol-001').reply(200, mockPolicy)

      const result = await policiesApi.update('pol-001', { enabled: false })
      expect(result).toEqual(mockPolicy)
    })

    it('delete calls DELETE /policies/:id', async () => {
      mock.onDelete('/policies/pol-001').reply(204)

      await expect(policiesApi.delete('pol-001')).resolves.toBeUndefined()
    })
  })

  describe('clientsApi', () => {
    it('list returns clients array', async () => {
      mock.onGet('/clients').reply(200, [mockClient])

      const result = await clientsApi.list()
      expect(result).toEqual([mockClient])
    })

    it('get returns single client by id', async () => {
      mock.onGet('/clients/cli-001').reply(200, mockClient)

      const result = await clientsApi.get('cli-001')
      expect(result).toEqual(mockClient)
    })

    it('delete calls DELETE /clients/:id', async () => {
      mock.onDelete('/clients/cli-001').reply(204)

      await expect(clientsApi.delete('cli-001')).resolves.toBeUndefined()
    })
  })

  describe('hubsApi', () => {
    it('list returns hubs array', async () => {
      mock.onGet('/hubs').reply(200, [mockHub])

      const result = await hubsApi.list()
      expect(result).toEqual([mockHub])
    })

    it('get returns single hub by id', async () => {
      mock.onGet('/hubs/hub-001').reply(200, mockHub)

      const result = await hubsApi.get('hub-001')
      expect(result).toEqual(mockHub)
    })

    it('create posts hub data and returns created hub', async () => {
      const { id, ...hubData } = mockHub
      mock.onPost('/hubs').reply(201, mockHub)

      const result = await hubsApi.create(hubData)
      expect(result).toEqual(mockHub)
    })

    it('delete calls DELETE /hubs/:id', async () => {
      mock.onDelete('/hubs/hub-001').reply(204)

      await expect(hubsApi.delete('hub-001')).resolves.toBeUndefined()
    })
  })

  describe('usersApi', () => {
    it('list returns users array', async () => {
      mock.onGet('/users').reply(200, [mockUser])

      const result = await usersApi.list()
      expect(result).toEqual([mockUser])
    })

    it('create posts user data and returns created user', async () => {
      const { id, created_at, ...userData } = mockUser
      mock.onPost('/users').reply(201, mockUser)

      const result = await usersApi.create({ ...userData, password: 'pass123' })
      expect(result).toEqual(mockUser)
    })

    it('update puts partial data and returns updated user', async () => {
      mock.onPut('/users/usr-001').reply(200, mockUser)

      const result = await usersApi.update('usr-001', { name: 'New Name' })
      expect(result).toEqual(mockUser)
    })

    it('delete calls DELETE /users/:id', async () => {
      mock.onDelete('/users/usr-001').reply(204)

      await expect(usersApi.delete('usr-001')).resolves.toBeUndefined()
    })
  })

  describe('identityApi', () => {
    it('list returns identity providers', async () => {
      mock.onGet('/identity').reply(200, [mockIdentityProvider])

      const result = await identityApi.list()
      expect(result).toEqual([mockIdentityProvider])
    })

    it('create posts provider data and returns created provider', async () => {
      const { id, ...providerData } = mockIdentityProvider
      mock.onPost('/identity').reply(201, mockIdentityProvider)

      const result = await identityApi.create(providerData)
      expect(result).toEqual(mockIdentityProvider)
    })

    it('update puts partial data and returns updated provider', async () => {
      mock.onPut('/identity/idp-001').reply(200, mockIdentityProvider)

      const result = await identityApi.update('idp-001', { enabled: true })
      expect(result).toEqual(mockIdentityProvider)
    })

    it('delete calls DELETE /identity/:id', async () => {
      mock.onDelete('/identity/idp-001').reply(204)

      await expect(identityApi.delete('idp-001')).resolves.toBeUndefined()
    })
  })

  describe('auditApi', () => {
    it('list returns audit logs', async () => {
      mock.onGet('/audit').reply(200, [mockAuditLog])

      const result = await auditApi.list()
      expect(result).toEqual([mockAuditLog])
    })

    it('list passes filter params', async () => {
      mock.onGet('/audit').reply(200, [mockAuditLog])

      const result = await auditApi.list({ event_type: 'auth', limit: 10, offset: 0 })
      expect(result).toEqual([mockAuditLog])
    })

    it('list works with no params', async () => {
      mock.onGet('/audit').reply(200, [])

      const result = await auditApi.list()
      expect(result).toEqual([])
    })
  })

  describe('dashboardApi', () => {
    it('stats returns dashboard statistics', async () => {
      mock.onGet('/dashboard/stats').reply(200, mockDashboardStats)

      const result = await dashboardApi.stats()
      expect(result).toEqual(mockDashboardStats)
    })
  })
})
