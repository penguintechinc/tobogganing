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
    // getStoredClaims is mocked directly below - no client-readable token
    // involved (access_token is an HttpOnly cookie the server manages).
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
  it('renders DevicesPage for perftest_cluster/devices', () => {
    render(
      <MemoryRouter initialEntries={['/m/perftest_cluster/devices']}>
        <Routes>
          <Route path="/m/:module/:view" element={<ModuleViewRoute />} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByTestId('devices-page')).toBeInTheDocument();
  });

  it('renders TestsPage for perftest_cluster/tests', () => {
    render(
      <MemoryRouter initialEntries={['/m/perftest_cluster/tests']}>
        <Routes>
          <Route path="/m/:module/:view" element={<ModuleViewRoute />} />
        </Routes>
      </MemoryRouter>
    );

    expect(screen.getByTestId('tests-page')).toBeInTheDocument();
  });

  it('renders StatsPage for perftest_cluster/stats', () => {
    render(
      <MemoryRouter initialEntries={['/m/perftest_cluster/stats']}>
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
