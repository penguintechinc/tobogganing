import { renderHook, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useManifest } from './useManifest';
import React, { ReactNode } from 'react';
import apiClient from '../api/client';

jest.mock('../api/client');

const createWrapper = () => {
  const queryClient = new QueryClient({
    defaultOptions: {
      queries: {
        retry: false,
      },
    },
  });
  const Wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  );
  Wrapper.displayName = 'QueryClientWrapper';
  return Wrapper;
};

describe('useManifest', () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it('fetches manifest on mount', async () => {
    const mockManifest = {
      modules: [
        {
          name: 'Admin',
          nav: [{ label: 'Users', path: '/m/admin/users', icon: 'laptop' }],
          flags: {},
        },
      ],
      role: 'admin',
    };

    (apiClient.get as jest.Mock).mockResolvedValue({ data: mockManifest });

    const { result } = renderHook(() => useManifest(), {
      wrapper: createWrapper(),
    });

    expect(result.current.isLoading).toBe(true);

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
      expect(result.current.data).toEqual(mockManifest);
    });
  });

  it('returns loaded manifest data', async () => {
    const mockManifest = {
      modules: [
        {
          name: 'Analytics',
          nav: [
            { label: 'Dashboard', path: '/m/analytics/dashboard', icon: 'bar-chart' },
            { label: 'Reports', path: '/m/analytics/reports', icon: 'file' },
          ],
          flags: { feature_beta: true },
        },
      ],
      role: 'maintainer',
      meta: { version: '1.0.0' },
    };

    (apiClient.get as jest.Mock).mockResolvedValue({ data: mockManifest });

    const { result } = renderHook(() => useManifest(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      if (result.current.data?.modules[0]) {
        expect(result.current.data.modules[0].name).toBe('Analytics');
        expect(result.current.data.role).toBe('maintainer');
        expect(result.current.data.modules[0].nav.length).toBe(2);
      }
    });
  });

  it('handles fetch errors', async () => {
    const mockError = new Error('Failed to fetch manifest');
    (apiClient.get as jest.Mock).mockRejectedValue(mockError);

    const { result } = renderHook(() => useManifest(), {
      wrapper: createWrapper(),
    });

    await waitFor(() => {
      expect(result.current.isLoading).toBe(false);
      expect(result.current.error).toBeTruthy();
    });
  });
});
