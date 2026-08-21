import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { RegionsPage } from './RegionsPage';
import * as c2cApi from '../../api/c2c';

jest.mock('../../api/c2c');

describe('RegionsPage', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    jest.clearAllMocks();
  });

  it('renders the page title', async () => {
    (c2cApi.listRegions as jest.Mock).mockResolvedValue([]);

    render(
      <QueryClientProvider client={queryClient}>
        <RegionsPage />
      </QueryClientProvider>
    );

    expect(screen.getByText('C2C Regions')).toBeInTheDocument();
    expect(screen.getByText('Region health summary and node inventory')).toBeInTheDocument();
  });

  it('loads and displays regions', async () => {
    const mockRegions = [
      {
        region: 'us-west-2',
        node_count: 5,
        healthy_count: 4,
        providers: ['aws'],
      },
    ];

    (c2cApi.listRegions as jest.Mock).mockResolvedValue(mockRegions);

    render(
      <QueryClientProvider client={queryClient}>
        <RegionsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('us-west-2')).toBeInTheDocument();
    });
  });

  it('displays region cards with health metrics', async () => {
    const mockRegions = [
      {
        region: 'us-west-2',
        node_count: 5,
        healthy_count: 4,
        providers: ['aws'],
      },
    ];

    (c2cApi.listRegions as jest.Mock).mockResolvedValue(mockRegions);

    render(
      <QueryClientProvider client={queryClient}>
        <RegionsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Total Nodes:')).toBeInTheDocument();
      expect(screen.getByText('Healthy:')).toBeInTheDocument();
      expect(screen.getByText('Health %:')).toBeInTheDocument();
    });
  });

  it('shows nodes when region is selected', async () => {
    const mockRegions = [
      {
        region: 'us-west-2',
        node_count: 2,
        healthy_count: 2,
        providers: ['aws'],
      },
    ];

    const mockNodes = [
      {
        id: 'node-1',
        region: 'us-west-2',
        name: 'node-1',
        engine_url: 'http://engine:8080',
        target: 'target.com',
        enabled: true,
      },
      {
        id: 'node-2',
        region: 'us-west-2',
        name: 'node-2',
        engine_url: undefined,
        target: 'target2.com',
        enabled: true,
      },
    ];

    (c2cApi.listRegions as jest.Mock).mockResolvedValue(mockRegions);
    (c2cApi.listVisibleNodes as jest.Mock).mockResolvedValue(mockNodes);

    render(
      <QueryClientProvider client={queryClient}>
        <RegionsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('us-west-2')).toBeInTheDocument();
    });

    const regionButton = screen.getByRole('button', { name: /us-west-2/i });
    fireEvent.click(regionButton);

    await waitFor(() => {
      expect(screen.getByText('Nodes in us-west-2')).toBeInTheDocument();
    });
  });

  it('handles redacted nodes gracefully', async () => {
    const mockRegions = [
      {
        region: 'us-west-2',
        node_count: 1,
        healthy_count: 1,
        providers: ['aws'],
      },
    ];

    const mockNodes = [
      {
        id: 'node-1',
        region: 'us-west-2',
        name: 'node-1',
        engine_url: undefined,
        target: 'target.com',
        enabled: true,
      },
    ];

    (c2cApi.listRegions as jest.Mock).mockResolvedValue(mockRegions);
    (c2cApi.listVisibleNodes as jest.Mock).mockResolvedValue(mockNodes);

    render(
      <QueryClientProvider client={queryClient}>
        <RegionsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('us-west-2')).toBeInTheDocument();
    });

    const regionButton = screen.getByRole('button', { name: /us-west-2/i });
    fireEvent.click(regionButton);

    await waitFor(() => {
      expect(screen.getByText('(redacted)')).toBeInTheDocument();
    });
  });

  it('collapses region node list when clicked again', async () => {
    const mockRegions = [
      {
        region: 'us-west-2',
        node_count: 1,
        healthy_count: 1,
        providers: ['aws'],
      },
    ];

    const mockNodes = [
      {
        id: 'node-1',
        region: 'us-west-2',
        name: 'node-1',
        engine_url: 'http://engine:8080',
        target: 'target.com',
        enabled: true,
      },
    ];

    (c2cApi.listRegions as jest.Mock).mockResolvedValue(mockRegions);
    (c2cApi.listVisibleNodes as jest.Mock).mockResolvedValue(mockNodes);

    render(
      <QueryClientProvider client={queryClient}>
        <RegionsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('us-west-2')).toBeInTheDocument();
    });

    const regionButton = screen.getByRole('button', { name: /us-west-2/i });
    fireEvent.click(regionButton);

    await waitFor(() => {
      expect(screen.getByText('Nodes in us-west-2')).toBeInTheDocument();
    });

    fireEvent.click(regionButton);

    await waitFor(() => {
      expect(screen.queryByText('Nodes in us-west-2')).not.toBeInTheDocument();
    });
  });

  it('shows empty state when no regions', async () => {
    (c2cApi.listRegions as jest.Mock).mockResolvedValue([]);

    render(
      <QueryClientProvider client={queryClient}>
        <RegionsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('No regions configured')).toBeInTheDocument();
    });
  });

  it('closes region node list when X button is clicked', async () => {
    const mockRegions = [
      {
        region: 'us-west-2',
        node_count: 1,
        healthy_count: 1,
        providers: ['aws'],
      },
    ];

    const mockNodes = [
      {
        id: 'node-1',
        region: 'us-west-2',
        name: 'node-1',
        engine_url: 'http://engine:8080',
        target: 'target.com',
        enabled: true,
      },
    ];

    (c2cApi.listRegions as jest.Mock).mockResolvedValue(mockRegions);
    (c2cApi.listVisibleNodes as jest.Mock).mockResolvedValue(mockNodes);

    render(
      <QueryClientProvider client={queryClient}>
        <RegionsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('us-west-2')).toBeInTheDocument();
    });

    const regionButton = screen.getByRole('button', { name: /us-west-2/i });
    fireEvent.click(regionButton);

    await waitFor(() => {
      expect(screen.getByText('Nodes in us-west-2')).toBeInTheDocument();
    });

    const closeButton = screen.getByRole('button', { name: '✕' });
    fireEvent.click(closeButton);

    await waitFor(() => {
      expect(screen.queryByText('Nodes in us-west-2')).not.toBeInTheDocument();
    });
  });
});
