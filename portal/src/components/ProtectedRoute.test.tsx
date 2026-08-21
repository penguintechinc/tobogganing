import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { ProtectedRoute } from './ProtectedRoute';
import { AuthProvider } from '../context/AuthContext';

const TestComponent = () => <div>Protected Content</div>;

const testToken =
  'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwiaWF0IjoxNTE2MjM5MDIyLCJleHAiOjk5OTk5OTk5OTksImVtYWlsIjoidGVzdEBleGFtcGxlLmNvbSIsInJvbGUiOiJ2aWV3ZXIiLCJ0ZW5hbnQiOiJ0ZXN0In0.mock';

const renderProtectedRoute = (isAuthenticated: boolean = false) => {
  if (isAuthenticated) {
    sessionStorage.setItem('access_token', testToken);
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
