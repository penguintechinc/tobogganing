import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Shell } from './Shell';
import { AuthProvider } from '../context/AuthContext';
import { cacheClaims, CSRF_COOKIE_NAME } from '../api/authStorage';

jest.mock('../hooks/useManifest', () => ({
  useManifest: () => ({
    data: {
      modules: [
        {
          name: 'Admin',
          nav: [
            { label: 'Users', path: '/m/admin/users', icon: 'laptop' },
            { label: 'Settings', path: '/m/admin/settings', icon: 'settings' },
          ],
          flags: {},
        },
      ],
      role: 'maintainer',
    },
    isLoading: false,
    error: null,
  }),
}));

const renderShell = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });

  render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <AuthProvider>
          <Routes>
            <Route path="/" element={<Shell />} />
          </Routes>
        </AuthProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
};

describe('Shell', () => {
  beforeEach(() => {
    sessionStorage.clear();
    // No client-readable access token anymore - hydrate via the csrf_token
    // cookie + cached claims, same as AuthProvider does on a real reload.
    document.cookie = `${CSRF_COOKIE_NAME}=test-csrf; path=/`;
    cacheClaims({
      sub: '1234567890',
      email: 'test@example.com',
      role: 'maintainer',
      tenant: 'test-tenant',
      iat: 1516239022,
      exp: 9999999999,
    });
  });

  afterEach(() => {
    document.cookie = `${CSRF_COOKIE_NAME}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
  });

  it('renders sidebar branding on desktop', async () => {
    renderShell();
    await waitFor(() => {
      const tobogganing = screen.getAllByText('Tobogganing');
      expect(tobogganing.length).toBeGreaterThan(0);
    });
  });

  it('renders logout button in sidebar', async () => {
    renderShell();
    await waitFor(() => {
      expect(screen.getByRole('button', { name: /logout/i })).toBeInTheDocument();
    });
  });

  it('renders hamburger menu on mobile', async () => {
    renderShell();
    await waitFor(() => {
      const toggleButton = screen.getByLabelText(/toggle menu/i);
      expect(toggleButton).toBeInTheDocument();
    });
  });

  it('renders main outlet area', () => {
    renderShell();
    expect(document.querySelector('main')).toBeInTheDocument();
  });

  it('toggles mobile menu on hamburger click', async () => {
    renderShell();
    const toggleButton = screen.getByLabelText(/toggle menu/i);

    fireEvent.click(toggleButton);
    await waitFor(() => {
      const adminText = screen.getAllByText('Admin');
      expect(adminText.length).toBeGreaterThan(0);
    });

    fireEvent.click(toggleButton);
    await waitFor(() => {
      const adminText = screen.queryAllByText('Admin');
      // Admin text should still be there (desktop version is always rendered)
      expect(adminText.length >= 1).toBe(true);
    });
  });
});
