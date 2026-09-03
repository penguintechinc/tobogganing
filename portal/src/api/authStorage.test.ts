import {
  CSRF_COOKIE_NAME,
  cacheClaims,
  clearCachedClaims,
  getCookie,
  hasSessionCookie,
  readCachedClaims,
} from './authStorage';

function setCookie(name: string, value: string): void {
  document.cookie = `${name}=${value}; path=/`;
}

function clearCookie(name: string): void {
  document.cookie = `${name}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
}

const sampleClaims = {
  sub: 'user-1',
  email: 'user@example.com',
  role: 'viewer',
  tenant: 't1',
  iat: 1,
  exp: 9999999999,
};

describe('authStorage', () => {
  beforeEach(() => {
    sessionStorage.clear();
    clearCookie(CSRF_COOKIE_NAME);
    clearCookie('other_cookie');
  });

  afterEach(() => {
    clearCookie(CSRF_COOKIE_NAME);
    clearCookie('other_cookie');
  });

  describe('getCookie', () => {
    it('returns null when the cookie is absent', () => {
      expect(getCookie('does_not_exist')).toBeNull();
    });

    it('returns the decoded value when the cookie is present', () => {
      setCookie('other_cookie', 'hello%20world');
      expect(getCookie('other_cookie')).toBe('hello world');
    });

    it('does not match a cookie whose name is a suffix of another', () => {
      setCookie('other_cookie', 'value1');
      expect(getCookie('cookie')).toBeNull();
    });
  });

  describe('hasSessionCookie', () => {
    it('is false with no csrf_token cookie', () => {
      expect(hasSessionCookie()).toBe(false);
    });

    it('is true once csrf_token cookie is set', () => {
      setCookie(CSRF_COOKIE_NAME, 'abc123');
      expect(hasSessionCookie()).toBe(true);
    });
  });

  describe('cacheClaims / readCachedClaims / clearCachedClaims', () => {
    it('round-trips claims when a session cookie is present', () => {
      setCookie(CSRF_COOKIE_NAME, 'abc123');
      cacheClaims(sampleClaims);
      expect(readCachedClaims()).toEqual(sampleClaims);
    });

    it('returns null and does not throw when nothing is cached', () => {
      setCookie(CSRF_COOKIE_NAME, 'abc123');
      expect(readCachedClaims()).toBeNull();
    });

    it('returns null and clears the cache when the session cookie is gone', () => {
      setCookie(CSRF_COOKIE_NAME, 'abc123');
      cacheClaims(sampleClaims);
      clearCookie(CSRF_COOKIE_NAME);

      expect(readCachedClaims()).toBeNull();
      expect(sessionStorage.getItem('auth_claims')).toBeNull();
    });

    it('returns null on malformed cached JSON without throwing', () => {
      setCookie(CSRF_COOKIE_NAME, 'abc123');
      sessionStorage.setItem('auth_claims', '{not-json');
      expect(readCachedClaims()).toBeNull();
    });

    it('clearCachedClaims removes the cache directly', () => {
      setCookie(CSRF_COOKIE_NAME, 'abc123');
      cacheClaims(sampleClaims);
      clearCachedClaims();
      expect(sessionStorage.getItem('auth_claims')).toBeNull();
    });
  });
});
