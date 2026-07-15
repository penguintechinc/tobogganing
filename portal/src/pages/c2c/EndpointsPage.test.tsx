import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { EndpointsPage } from './EndpointsPage';
import * as c2cApi from '../../api/c2c';

jest.mock('../../api/c2c');
jest.mock('../../hooks/useRole', () => ({
  useRole: () => ({ canWrite: () => true }),
}));

describe('EndpointsPage', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    jest.clearAllMocks();
  });

  it('renders the page title and description', async () => {
    (c2cApi.listEndpoints as jest.Mock).mockResolvedValue([]);

    render(
      <QueryClientProvider client={queryClient}>
        <EndpointsPage />
      </QueryClientProvider>
    );

    expect(screen.getByText('C2C Nodes')).toBeInTheDocument();
    expect(
      screen.getByText('Manage cluster-to-cluster test endpoints')
    ).toBeInTheDocument();
  });

  it('renders a create button when canWrite is true', async () => {
    (c2cApi.listEndpoints as jest.Mock).mockResolvedValue([]);

    render(
      <QueryClientProvider client={queryClient}>
        <EndpointsPage />
      </QueryClientProvider>
    );

    const createButton = screen.getByText('Create Endpoint');
    expect(createButton).toBeInTheDocument();
  });

  it('loads and displays endpoints', async () => {
    const mockEndpoints = [
      {
        id: 'ep-1',
        region: 'us-west-2',
        name: 'node-1',
        engine_url: 'http://engine:8080',
        target: 'target.com',
        enabled: true,
      },
    ];

    (c2cApi.listEndpoints as jest.Mock).mockResolvedValue(mockEndpoints);

    render(
      <QueryClientProvider client={queryClient}>
        <EndpointsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('node-1')).toBeInTheDocument();
    });
  });

  it('shows empty state when no endpoints', async () => {
    (c2cApi.listEndpoints as jest.Mock).mockResolvedValue([]);

    render(
      <QueryClientProvider client={queryClient}>
        <EndpointsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      const dataTable = screen.queryByRole('table');
      if (dataTable) {
        const rows = dataTable.querySelectorAll('tbody tr');
        expect(rows.length).toBe(0);
      }
    });
  });

  it('toggles form visibility', async () => {
    (c2cApi.listEndpoints as jest.Mock).mockResolvedValue([]);

    render(
      <QueryClientProvider client={queryClient}>
        <EndpointsPage />
      </QueryClientProvider>
    );

    const createButton = screen.getByText('Create Endpoint');
    fireEvent.click(createButton);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('e.g., us-west-2')).toBeInTheDocument();
    });
  });
});
