import { parseJwt, getStoredToken, getStoredClaims, login, logout } from './auth';
import apiClient from './client';

jest.mock('./client');

const mockedApiClient = apiClient as jest.Mocked<typeof apiClient>;

describe('auth utilities', () => {
  let consoleLogSpy: jest.SpyInstance;

  beforeEach(() => {
    jest.clearAllMocks();
    sessionStorage.clear();
    consoleLogSpy = jest.spyOn(console, 'log').mockImplementation();
  });

  afterEach(() => {
    consoleLogSpy.mockRestore();
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

  describe('token storage', () => {
    it('retrieves stored token', () => {
      sessionStorage.setItem('access_token', 'test-token-xyz');
      expect(getStoredToken()).toBe('test-token-xyz');
    });

    it('returns null when no token stored', () => {
      expect(getStoredToken()).toBeNull();
    });

    it('retrieves stored claims', () => {
      const token =
        'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwiZW1haWwiOiJ0ZXN0QGV4YW1wbGUuY29tIiwicm9sZSI6InZpZXdlciIsInRlbmFudCI6InQxIiwiaWF0IjoxNTE2MjM5MDIyLCJleHAiOjk5OTk5OTk5OTl9.mock';
      sessionStorage.setItem('access_token', token);

      const claims = getStoredClaims();
      expect(claims?.email).toBe('test@example.com');
    });

    it('returns null when no stored claims', () => {
      expect(getStoredClaims()).toBeNull();
    });
  });

  describe('login', () => {
    it('stores tokens on successful login', async () => {
      const mockToken =
        'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwiZW1haWwiOiJ0ZXN0QGV4YW1wbGUuY29tIiwicm9sZSI6Im1haW50YWluZXIiLCJ0ZW5hbnQiOiJ0MSIsImlhdCI6MTUxNjIzOTAyMiwiZXhwIjo5OTk5OTk5OTk5fQ.mock';
      const mockRefreshToken = 'refresh-token-xyz';

      mockedApiClient.post = jest.fn().mockResolvedValue({
        data: {
          access_token: mockToken,
          refresh_token: mockRefreshToken,
          expires_in: 3600,
          token_type: 'Bearer',
        },
      });

      const result = await login('test@example.com', 'password123');

      expect(result.mfaRequired).toBe(false);
      expect(result.claims?.email).toBe('test@example.com');
      expect(sessionStorage.getItem('access_token')).toBe(mockToken);
      expect(sessionStorage.getItem('refresh_token')).toBe(mockRefreshToken);
    });

    it('handles MFA required response', async () => {
      mockedApiClient.post = jest.fn().mockResolvedValue({
        data: { mfa_required: true },
      });

      const result = await login('test@example.com', 'password123');

      expect(result.mfaRequired).toBe(true);
      expect(result.claims).toBeUndefined();
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
    it('clears tokens on logout', async () => {
      sessionStorage.setItem('access_token', 'token-xyz');
      sessionStorage.setItem('refresh_token', 'refresh-xyz');

      mockedApiClient.post = jest.fn().mockResolvedValue({});

      await logout();

      expect(sessionStorage.getItem('access_token')).toBeNull();
      expect(sessionStorage.getItem('refresh_token')).toBeNull();
    });

    it('handles logout API failure gracefully', async () => {
      sessionStorage.setItem('access_token', 'token-xyz');
      sessionStorage.setItem('refresh_token', 'refresh-xyz');

      mockedApiClient.post = jest.fn().mockRejectedValue(new Error('API error'));

      await logout();

      expect(sessionStorage.getItem('access_token')).toBeNull();
      expect(sessionStorage.getItem('refresh_token')).toBeNull();
    });

    it('handles logout without refresh token', async () => {
      mockedApiClient.post = jest.fn();

      await logout();

      expect(mockedApiClient.post).not.toHaveBeenCalled();
    });
  });
});
