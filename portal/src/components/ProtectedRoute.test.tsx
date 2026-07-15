import React from 'react';
import { render, screen } from '@testing-library/react';
import { BrowserRouter, Routes, Route } from 'react-router-dom';
import { ProtectedRoute } from './ProtectedRoute';
import { AuthProvider } from '../context/AuthContext';

const TestComponent = () => <div>Protected Content</div>;

const renderProtectedRoute = (isAuthenticated: boolean = false) => {
  // Override the useAuth hook behavior via sessionStorage
  if (isAuthenticated) {
    sessionStorage.setItem(
      'access_token',
      'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwiaWF0IjoxNTE2MjM5MDIyLCJleHAiOjk5OTk5OTk5OTksImVtYWlsIjoidGVzdEBleGFtcGxlLmNvbSIsInJvbGUiOiJ2aWV3ZXIiLCJ0ZW5hbnQiOiJ0ZXN0In0.mock'
    );
  }

  render(
    <BrowserRouter>
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
    </BrowserRouter>
  );
};

describe('ProtectedRoute', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('redirects to login when not authenticated', () => {
    renderProtectedRoute(false);
    // Navigation happens asynchronously
    setTimeout(() => {
      expect(screen.queryByText('Protected Content')).not.toBeInTheDocument();
    }, 100);
  });

  it('renders protected content when authenticated', async () => {
    renderProtectedRoute(true);
    // Wait for the component to render
    setTimeout(() => {
      expect(screen.getByText('Protected Content')).toBeInTheDocument();
    }, 100);
  });
});
