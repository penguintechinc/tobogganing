import { parseJwt, getStoredToken, getStoredClaims } from './auth';

describe('auth utilities', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

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
