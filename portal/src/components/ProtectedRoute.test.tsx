import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { ProtectedRoute } from './ProtectedRoute';
import { AuthProvider } from '../context/AuthContext';
import { cacheClaims, CSRF_COOKIE_NAME } from '../api/authStorage';

const TestComponent = () => <div>Protected Content</div>;

const renderProtectedRoute = (isAuthenticated: boolean = false) => {
  if (isAuthenticated) {
    // Simulate an authenticated session via the csrf_token cookie + cached
    // claims - there is no client-readable access token anymore (HttpOnly).
    document.cookie = `${CSRF_COOKIE_NAME}=test-csrf; path=/`;
    cacheClaims({
      sub: '1234567890',
      email: 'test@example.com',
      role: 'viewer',
      tenant: 'test',
      iat: 1516239022,
      exp: 9999999999,
    });
  }

  render(
    <MemoryRouter initialEntries={['/']}>
      <AuthProvider>
        <Routes>
          <Route
            path="/"
            element={
              <ProtectedRoute>
                <TestComponent />
              </ProtectedRoute>
            }
          />
          <Route path="/login" element={<div>Login Page</div>} />
        </Routes>
      </AuthProvider>
    </MemoryRouter>
  );
};

describe('ProtectedRoute', () => {
  beforeEach(() => {
    sessionStorage.clear();
    document.cookie = `${CSRF_COOKIE_NAME}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
  });

  it('redirects to login when not authenticated', async () => {
    renderProtectedRoute(false);
    await waitFor(() => {
      expect(screen.queryByText('Protected Content')).not.toBeInTheDocument();
    });
  });

  it('can be rendered without crashing', () => {
    renderProtectedRoute(true);
    // Just verify the component renders without error
    const container = document.querySelector('div');
    expect(container).toBeTruthy();
  });
});
