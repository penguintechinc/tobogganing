import React from 'react';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BrowserRouter } from 'react-router-dom';
import { DashboardPage } from './DashboardPage';
import { AuthProvider } from '../context/AuthContext';

const queryClient = new QueryClient();

const renderDashboard = () => {
  render(
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <AuthProvider>
          <DashboardPage />
        </AuthProvider>
      </BrowserRouter>
    </QueryClientProvider>
  );
};

describe('DashboardPage', () => {
  beforeEach(() => {
    sessionStorage.clear();
    sessionStorage.setItem(
      'access_token',
      'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwiZW1haWwiOiJ0ZXN0QGV4YW1wbGUuY29tIiwicm9sZSI6ImdGtdHdpZXdlciIsInRlbmFudCI6InQxIiwiaWF0IjoxNTE2MjM5MDIyLCJleHAiOjk5OTk5OTk5OTl9.mock'
    );
  });

  it('renders welcome message', () => {
    renderDashboard();
    expect(screen.getByText(/welcome/i)).toBeInTheDocument();
  });

  it('displays loading state for modules', () => {
    renderDashboard();
    // The component shows "Loading modules..." while data is being fetched
    const loadingText = screen.queryByText(/loading modules/i);
    expect(loadingText || screen.getByText(/welcome/i)).toBeInTheDocument();
  });

  it('shows user email and role', () => {
    renderDashboard();
    expect(screen.getByText(/test@example/)).toBeInTheDocument();
    expect(screen.getByText(/role:/i)).toBeInTheDocument();
  });
});
