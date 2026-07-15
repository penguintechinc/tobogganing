import { renderHook } from '@testing-library/react';
import { useRole } from './useRole';
import { AuthProvider } from '../context/AuthContext';
import React, { ReactNode } from 'react';

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
  });

  it('returns viewer role when no user logged in', () => {
    const { result } = renderHook(() => useRole(), {
      wrapper: createWrapper(),
    });

    expect(result.current.role).toBe('viewer');
    expect(result.current.canWrite()).toBe(false);
  });

  it('returns true for canWrite when role is not viewer', () => {
    sessionStorage.setItem(
      'access_token',
      'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwiZW1haWwiOiJ0ZXN0QGV4YW1wbGUuY29tIiwicm9sZSI6Im1haW50YWluZXIiLCJ0ZW5hbnQiOiJ0MSIsImlhdCI6MTUxNjIzOTAyMiwiZXhwIjo5OTk5OTk5OTk5fQ.mock'
    );

    const { result } = renderHook(() => useRole(), {
      wrapper: createWrapper(),
    });

    expect(result.current.role).toBe('maintainer');
    expect(result.current.canWrite()).toBe(true);
  });

  it('returns admin role with write access', () => {
    sessionStorage.setItem(
      'access_token',
      'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwiZW1haWwiOiJ0ZXN0QGV4YW1wbGUuY29tIiwicm9sZSI6ImFkbWluIiwidGVuYW50IjoidDEiLCJpYXQiOjE1MTYyMzkwMjIsImV4cCI6OTk5OTk5OTk5OX0.mock'
    );

    const { result } = renderHook(() => useRole(), {
      wrapper: createWrapper(),
    });

    expect(result.current.role).toBe('admin');
    expect(result.current.canWrite()).toBe(true);
  });
});
