import { parseJwt, getStoredClaims, login, logout } from './auth';
import apiClient from './client';

jest.mock('./client');

const mockedApiClient = apiClient as jest.Mocked<typeof apiClient>;

function setCsrfCookie(value: string): void {
  document.cookie = `csrf_token=${value}; path=/`;
}

function clearCsrfCookie(): void {
  document.cookie = 'csrf_token=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT';
}

describe('auth utilities', () => {
  let consoleLogSpy: jest.SpyInstance;

  beforeEach(() => {
    jest.clearAllMocks();
    sessionStorage.clear();
    clearCsrfCookie();
    consoleLogSpy = jest.spyOn(console, 'log').mockImplementation();
  });

  afterEach(() => {
    consoleLogSpy.mockRestore();
    clearCsrfCookie();
  });

  describe('parseJwt', () => {
    it('parses JWT token correctly', () => {
      const token =
        'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwiZW1haWwiOiJ0ZXN0QGV4YW1wbGUuY29tIiwicm9sZSI6ImFkbWluIiwidGVuYW50IjoidGVzdC10ZW5hbnQiLCJpYXQiOjE1MTYyMzkwMjIsImV4cCI6OTk5OTk5OTk5OX0.mock';

      const claims = parseJwt(token);
      expect(claims.email).toBe('test@example.com');
      expect(claims.role).toBe('admin');
      expect(claims.tenant).toBe('test-tenant');
    });

    it('throws on invalid token format', () => {
      expect(() => parseJwt('invalid.token')).toThrow();
    });

    it('throws on malformed token', () => {
      expect(() => parseJwt('a.b')).toThrow();
    });
  });

  describe('getStoredClaims', () => {
    it('returns null when no session cookie is present, even with a stale cache', () => {
      sessionStorage.setItem(
        'auth_claims',
        JSON.stringify({
          sub: '1',
          email: 'a@b.co',
          role: 'viewer',
          tenant: 't1',
          iat: 1,
          exp: 9999999999,
        })
      );
      // No csrf_token cookie set -> no active server session
      expect(getStoredClaims()).toBeNull();
      // Stale cache is also cleared as a side effect
      expect(sessionStorage.getItem('auth_claims')).toBeNull();
    });

    it('returns cached claims when the session cookie is present', () => {
      setCsrfCookie('csrf-1');
      sessionStorage.setItem(
        'auth_claims',
        JSON.stringify({
          sub: '1',
          email: 'test@example.com',
          role: 'viewer',
          tenant: 't1',
          iat: 1,
          exp: 9999999999,
        })
      );

      const claims = getStoredClaims();
      expect(claims?.email).toBe('test@example.com');
    });

    it('returns null when session cookie is present but nothing cached yet', () => {
      setCsrfCookie('csrf-1');
      expect(getStoredClaims()).toBeNull();
    });
  });

  describe('login', () => {
    it('never persists access_token/refresh_token to sessionStorage', async () => {
      const mockToken =
        'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwiZW1haWwiOiJ0ZXN0QGV4YW1wbGUuY29tIiwicm9sZSI6Im1haW50YWluZXIiLCJ0ZW5hbnQiOiJ0MSIsImlhdCI6MTUxNjIzOTAyMiwiZXhwIjo5OTk5OTk5OTk5fQ.mock';

      mockedApiClient.post = jest.fn().mockResolvedValue({
        data: {
          access_token: mockToken,
          refresh_token: 'refresh-token-xyz',
          expires_in: 3600,
          token_type: 'Bearer',
        },
      });

      const result = await login('test@example.com', 'password123');

      expect(result.mfaRequired).toBe(false);
      expect(result.claims?.email).toBe('test@example.com');
      // Tokens are HttpOnly cookies set by the server - never in sessionStorage
      expect(sessionStorage.getItem('access_token')).toBeNull();
      expect(sessionStorage.getItem('refresh_token')).toBeNull();
    });

    it('caches only the decoded claims (not the token) for UI hydration', async () => {
      setCsrfCookie('csrf-after-login');
      const mockToken =
        'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwiZW1haWwiOiJ0ZXN0QGV4YW1wbGUuY29tIiwicm9sZSI6ImFkbWluIiwidGVuYW50IjoidDEiLCJpYXQiOjE1MTYyMzkwMjIsImV4cCI6OTk5OTk5OTk5OX0.mock';

      mockedApiClient.post = jest.fn().mockResolvedValue({
        data: { access_token: mockToken, refresh_token: 'r1' },
      });

      await login('test@example.com', 'password123');

      const cached = JSON.parse(sessionStorage.getItem('auth_claims') ?? 'null');
      expect(cached?.email).toBe('test@example.com');
      expect(sessionStorage.getItem('auth_claims')).not.toContain(mockToken);
    });

    it('handles MFA required response', async () => {
      mockedApiClient.post = jest.fn().mockResolvedValue({
        data: { mfa_required: true },
      });

      const result = await login('test@example.com', 'password123');

      expect(result.mfaRequired).toBe(true);
      expect(result.claims).toBeUndefined();
      expect(sessionStorage.getItem('auth_claims')).toBeNull();
    });

    it('handles login with MFA token', async () => {
      const mockToken =
        'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwiZW1haWwiOiJ0ZXN0QGV4YW1wbGUuY29tIiwicm9sZSI6ImFkbWluIiwidGVuYW50IjoidDEiLCJpYXQiOjE1MTYyMzkwMjIsImV4cCI6OTk5OTk5OTk5OX0.mock';

      mockedApiClient.post = jest.fn().mockResolvedValue({
        data: {
          access_token: mockToken,
          refresh_token: 'refresh-xyz',
        },
      });

      const result = await login('test@example.com', 'password123', '123456');

      expect(mockedApiClient.post).toHaveBeenCalledWith('/auth/login', {
        email: 'test@example.com',
        password: 'password123',
        mfa_token: '123456',
      });
      expect(result.mfaRequired).toBe(false);
    });

    it('handles login errors', async () => {
      const error = new Error('Invalid credentials');
      mockedApiClient.post = jest.fn().mockRejectedValue(error);

      await expect(login('test@example.com', 'wrongpassword')).rejects.toThrow();
    });
  });

  describe('logout', () => {
    it('calls the logout endpoint with no body (server reads the refresh_token cookie)', async () => {
      mockedApiClient.post = jest.fn().mockResolvedValue({});

      await logout();

      expect(mockedApiClient.post).toHaveBeenCalledWith('/auth/logout');
    });

    it('clears cached claims on logout', async () => {
      setCsrfCookie('csrf-1');
      sessionStorage.setItem(
        'auth_claims',
        JSON.stringify({
          sub: '1',
          email: 'a@b.co',
          role: 'viewer',
          tenant: 't1',
          iat: 1,
          exp: 9999999999,
        })
      );
      mockedApiClient.post = jest.fn().mockResolvedValue({});

      await logout();

      expect(sessionStorage.getItem('auth_claims')).toBeNull();
    });

    it('clears cached claims even when the logout API call fails', async () => {
      setCsrfCookie('csrf-1');
      sessionStorage.setItem(
        'auth_claims',
        JSON.stringify({
          sub: '1',
          email: 'a@b.co',
          role: 'viewer',
          tenant: 't1',
          iat: 1,
          exp: 9999999999,
        })
      );
      mockedApiClient.post = jest.fn().mockRejectedValue(new Error('API error'));

      await logout();

      expect(sessionStorage.getItem('auth_claims')).toBeNull();
    });
  });
});

describe('parseJwt claim normalization', () => {
  const makeToken = (payload: Record<string, unknown>): string => {
    const b64 = btoa(JSON.stringify(payload))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
      .replace(/=+$/, '');
    return `h.${b64}.s`;
  };

  it('derives role from roles array and email fallback from sub (real backend tokens)', () => {
    const claims = parseJwt(
      makeToken({ sub: 'user-1', tenant: 't1', roles: ['admin'], exp: 9999999999 })
    );
    expect(claims.role).toBe('admin');
    expect(claims.email).toBe('user-1');
  });

  it('keeps singular role and explicit email when present', () => {
    const claims = parseJwt(
      makeToken({ sub: 'u', email: 'a@b.co', role: 'reporter', tenant: 't1' })
    );
    expect(claims.role).toBe('reporter');
    expect(claims.email).toBe('a@b.co');
  });

  it('defaults role to viewer when no role claims exist', () => {
    const claims = parseJwt(makeToken({ sub: 'u', tenant: 't1' }));
    expect(claims.role).toBe('viewer');
  });
});
