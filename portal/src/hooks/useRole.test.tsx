import { renderHook } from '@testing-library/react';
import { useRole } from './useRole';
import { AuthProvider } from '../context/AuthContext';
import { cacheClaims, CSRF_COOKIE_NAME } from '../api/authStorage';
import React, { ReactNode } from 'react';

function clearSessionCookie(): void {
  document.cookie = `${CSRF_COOKIE_NAME}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
}

const createWrapper = () => {
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <AuthProvider>{children}</AuthProvider>
  );
  Wrapper.displayName = 'AuthWrapper';
  return Wrapper;
};

describe('useRole', () => {
  beforeEach(() => {
    sessionStorage.clear();
    clearSessionCookie();
  });

  afterEach(() => {
    clearSessionCookie();
  });

  it('returns viewer role when no user logged in', () => {
    const { result } = renderHook(() => useRole(), {
      wrapper: createWrapper(),
    });

    expect(result.current.role).toBe('viewer');
    expect(result.current.canWrite()).toBe(false);
  });

  it('returns true for canWrite when role is not viewer', () => {
    // No client-readable access token anymore - hydrate via the csrf_token
    // cookie + cached claims, same as AuthProvider does on a real reload.
    document.cookie = `${CSRF_COOKIE_NAME}=test-csrf; path=/`;
    cacheClaims({
      sub: '1234567890',
      email: 'test@example.com',
      role: 'maintainer',
      tenant: 't1',
      iat: 1516239022,
      exp: 9999999999,
    });

    const { result } = renderHook(() => useRole(), {
      wrapper: createWrapper(),
    });

    expect(result.current.role).toBe('maintainer');
    expect(result.current.canWrite()).toBe(true);
  });

  it('returns admin role with write access', () => {
    document.cookie = `${CSRF_COOKIE_NAME}=test-csrf; path=/`;
    cacheClaims({
      sub: '1234567890',
      email: 'test@example.com',
      role: 'admin',
      tenant: 't1',
      iat: 1516239022,
      exp: 9999999999,
    });

    const { result } = renderHook(() => useRole(), {
      wrapper: createWrapper(),
    });

    expect(result.current.role).toBe('admin');
    expect(result.current.canWrite()).toBe(true);
  });
});
