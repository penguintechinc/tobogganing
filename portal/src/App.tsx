import React from 'react';
import { BrowserRouter, Routes, Route, useParams } from 'react-router-dom';
import { QueryClientProvider, QueryClient } from '@tanstack/react-query';
import { AuthProvider } from './context/AuthContext';
import { LoginPage } from './pages/LoginPage';
import { DashboardPage } from './pages/DashboardPage';
import { Shell } from './components/Shell';
import { ProtectedRoute } from './components/ProtectedRoute';
import { PlaceholderView } from './components/PlaceholderView';
import { DevicesPage } from './pages/waddleperf/DevicesPage';
import { TestsPage } from './pages/waddleperf/TestsPage';
import { StatsPage } from './pages/waddleperf/StatsPage';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<LoginPage />} />
            <Route
              element={
                <ProtectedRoute>
                  <Shell />
                </ProtectedRoute>
              }
            >
              <Route path="/" element={<DashboardPage />} />
              <Route path="/m/:module/:view" element={<ModuleViewRoute />} />
            </Route>
          </Routes>
        </BrowserRouter>
      </AuthProvider>
    </QueryClientProvider>
  );
}

export function ModuleViewRoute() {
  const { module, view } = useParams<{ module: string; view: string }>();

  if (!module || !view) {
    return null;
  }

  if (module === 'waddleperf_cluster') {
    if (view === 'devices') {
      return <DevicesPage />;
    }
    if (view === 'tests') {
      return <TestsPage />;
    }
    if (view === 'stats') {
      return <StatsPage />;
    }
  }

  return <PlaceholderView module={module} view={view} />;
}
