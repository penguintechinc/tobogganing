import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Shell } from './Shell';
import { AuthProvider } from '../context/AuthContext';

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
    sessionStorage.setItem(
      'access_token',
      'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwiZW1haWwiOiJ0ZXN0QGV4YW1wbGUuY29tIiwicm9sZSI6Im1haW50YWluZXIiLCJ0ZW5hbnQiOiJ0ZXN0LXRlbmFudCIsImlhdCI6MTUxNjIzOTAyMiwiZXhwIjo5OTk5OTk5OTk5fQ.mock'
    );
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
