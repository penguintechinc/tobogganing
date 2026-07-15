import React from 'react';
import { render, screen } from '@testing-library/react';
import { BrowserRouter } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Shell } from './Shell';
import { AuthProvider } from '../context/AuthContext';

const queryClient = new QueryClient();

const renderShell = () => {
  render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <Shell />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
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

  it('renders sidebar on desktop', () => {
    renderShell();
    // The sidebar renders but may not be visible due to hidden lg:block
    expect(screen.getByText('Tobogganing')).toBeInTheDocument();
  });

  it('renders logout button in sidebar', () => {
    renderShell();
    expect(screen.getByRole('button', { name: /logout/i })).toBeInTheDocument();
  });

  it('renders hamburger menu on mobile', () => {
    renderShell();
    const toggleButton = screen.getByLabelText(/toggle menu/i);
    expect(toggleButton).toBeInTheDocument();
  });

  it('renders main outlet area', () => {
    renderShell();
    // Shell is rendered with Outlet, which will render child routes
    expect(document.querySelector('main')).toBeInTheDocument();
  });
});
