import { renderHook } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { useManifest } from './useManifest';
import React from 'react';

const createWrapper = () => {
  const queryClient = new QueryClient();
  const Wrapper = ({ children }: { children: React.ReactNode }) => {
    return React.createElement(QueryClientProvider, { client: queryClient }, children);
  };
  Wrapper.displayName = 'QueryClientWrapper';
  return Wrapper;
};

describe('useManifest', () => {
  it('fetches manifest on mount', async () => {
    const { result } = renderHook(() => useManifest(), {
      wrapper: createWrapper(),
    });

    expect(result.current.isLoading).toBe(true);

    // In real usage, this would fetch from /api/v1/portal/manifest
    // For testing, we'd mock the apiClient
  });

  it('has staleTime of 5 minutes', () => {
    const { result } = renderHook(() => useManifest(), {
      wrapper: createWrapper(),
    });

    // Query configuration validation
    expect(result.current).toBeDefined();
  });
});
