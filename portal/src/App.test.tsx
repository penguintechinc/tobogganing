import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter, Routes, Route } from 'react-router-dom';
import { App, ModuleViewRoute } from './App';

jest.mock('./hooks/useManifest', () => ({
  useManifest: () => ({
    data: {
      modules: [],
      role: 'viewer',
    },
    isLoading: false,
    error: null,
  }),
}));

jest.mock('./api/auth', () => ({
  getStoredClaims: jest.fn(() => null),
  login: jest.fn(),
  logout: jest.fn(),
}));

// Mock the page components to avoid nested router issues
jest.mock('./pages/waddleperf/DevicesPage', () => ({
  DevicesPage: () => <div data-testid="devices-page">Devices Page</div>,
}));

jest.mock('./pages/waddleperf/TestsPage', () => ({
  TestsPage: () => <div data-testid="tests-page">Tests Page</div>,
}));

jest.mock('./pages/waddleperf/StatsPage', () => ({
  StatsPage: () => <div data-testid="stats-page">Stats Page</div>,
}));

jest.mock('./components/PlaceholderView', () => ({
  PlaceholderView: ({ module, view }: { module: string; view: string }) => (
    <div data-testid="placeholder-view">
      {module}/{view}
    </div>
  ),
}));

describe('App', () => {
  beforeEach(() => {
    sessionStorage.clear();
  });

  it('renders login page when not authenticated', () => {
    const { container } = render(<App />);
    expect(container).toBeTruthy();
  });

  it('renders dashboard when authenticated', async () => {
    sessionStorage.setItem(
      'access_token',
      'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIiwiZW1haWwiOiJ0ZXN0QGV4YW1wbGUuY29tIiwicm9sZSI6InZpZXdlciIsInRlbmFudCI6InQxIiwiaWF0IjoxNTE2MjM5MDIyLCJleHAiOjk5OTk5OTk5OTl9.mock'
    );

    // eslint-disable-next-line @typescript-eslint/no-var-requires
    const authApi = require('./api/auth');
    authApi.getStoredClaims.mockReturnValue({
      sub: '1234567890',
      email: 'test@example.com',
      role: 'viewer',
      tenant: 't1',
      iat: 1516239022,
      exp: 9999999999,
    });

    render(<App />);

    await waitFor(() => {
      expect(screen.getByText(/welcome/i)).toBeInTheDocument();
    });
  });

  it('renders with QueryClient provider', () => {
    const { container } = render(<App />);
    expect(container).toBeTruthy();
  });
});

describe('ModuleViewRoute', () => {
  it('renders DevicesPage for waddleperf_cluster/devices', () => {
    render(
      <MemoryRouter initialEntries={['/m/waddleperf_cluster/devices']}>
        <Routes>
          <Route path="/m/:module/:view" element={<ModuleViewRoute />} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByTestId('devices-page')).toBeInTheDocument();
  });

  it('renders TestsPage for waddleperf_cluster/tests', () => {
    render(
      <MemoryRouter initialEntries={['/m/waddleperf_cluster/tests']}>
        <Routes>
          <Route path="/m/:module/:view" element={<ModuleViewRoute />} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByTestId('tests-page')).toBeInTheDocument();
  });

  it('renders StatsPage for waddleperf_cluster/stats', () => {
    render(
      <MemoryRouter initialEntries={['/m/waddleperf_cluster/stats']}>
        <Routes>
          <Route path="/m/:module/:view" element={<ModuleViewRoute />} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByTestId('stats-page')).toBeInTheDocument();
  });

  it('renders PlaceholderView for unknown module', () => {
    render(
      <MemoryRouter initialEntries={['/m/unknown_module/unknown_view']}>
        <Routes>
          <Route path="/m/:module/:view" element={<ModuleViewRoute />} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByTestId('placeholder-view')).toBeInTheDocument();
    expect(screen.getByText('unknown_module/unknown_view')).toBeInTheDocument();
  });

  it('renders null when module or view is missing', () => {
    const { container } = render(
      <MemoryRouter initialEntries={['/m']}>
        <Routes>
          <Route path="/m" element={<ModuleViewRoute />} />
        </Routes>
      </MemoryRouter>
    );

    // When null is returned, the container should be empty
    expect(container.textContent).toBe('');
  });
});
