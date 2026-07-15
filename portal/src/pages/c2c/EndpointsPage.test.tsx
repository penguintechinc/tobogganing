import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { EndpointsPage } from './EndpointsPage';
import * as c2cApi from '../../api/c2c';
import { useRole } from '../../hooks/useRole';

jest.mock('../../api/c2c');
jest.mock('../../hooks/useRole', () => ({ useRole: jest.fn() }));

const mockUseRole = useRole as jest.Mock;

describe('EndpointsPage', () => {
  let queryClient: QueryClient;

  const mockEndpoints = [
    {
      id: 'ep-1',
      region: 'us-west-2',
      name: 'node-1',
      engine_url: 'http://engine:8080',
      target: 'target.com',
      enabled: true,
      visibility: 'public',
      provider: 'aws',
    },
    {
      id: 'ep-2',
      region: 'eu-central-1',
      name: 'node-2',
      engine_url: 'http://engine2:8080',
      target: 'target2.com',
      enabled: false,
      visibility: 'private',
      provider: 'gcp',
    },
  ];

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
    });
    jest.clearAllMocks();
    (c2cApi.listEndpoints as jest.Mock).mockResolvedValue(mockEndpoints);
    (c2cApi.createEndpoint as jest.Mock).mockResolvedValue({ id: 'ep-3', ...mockEndpoints[0] });
    (c2cApi.deleteEndpoint as jest.Mock).mockResolvedValue(undefined);
    mockUseRole.mockReturnValue({ canWrite: () => true });
  });

  it('renders the page title and description', async () => {

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

    render(
      <QueryClientProvider client={queryClient}>
        <EndpointsPage />
      </QueryClientProvider>
    );

    const createButton = screen.getByText('Create Endpoint');
    expect(createButton).toBeInTheDocument();
  });

  it('hides create button when canWrite is false', async () => {
    mockUseRole.mockReturnValue({ canWrite: () => false });

    render(
      <QueryClientProvider client={queryClient}>
        <EndpointsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.queryByText('Create Endpoint')).not.toBeInTheDocument();
    });
  });

  it('loads and displays endpoints', async () => {

    render(
      <QueryClientProvider client={queryClient}>
        <EndpointsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('node-1')).toBeInTheDocument();
      expect(screen.getByText('node-2')).toBeInTheDocument();
      expect(screen.getByText('us-west-2')).toBeInTheDocument();
      expect(screen.getByText('eu-central-1')).toBeInTheDocument();
    });
  });

  it('displays health badge for healthy endpoint', async () => {

    render(
      <QueryClientProvider client={queryClient}>
        <EndpointsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      const healthyBadges = screen.getAllByText('Healthy');
      expect(healthyBadges.length).toBeGreaterThan(0);
    });
  });

  it('displays health badge for offline endpoint', async () => {

    render(
      <QueryClientProvider client={queryClient}>
        <EndpointsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      const offlineBadges = screen.getAllByText('Offline');
      expect(offlineBadges.length).toBeGreaterThan(0);
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
      expect(screen.getByText('No data available')).toBeInTheDocument();
    });
  });

  it('toggles form visibility', async () => {

    render(
      <QueryClientProvider client={queryClient}>
        <EndpointsPage />
      </QueryClientProvider>
    );

    const createButton = screen.getByText('Create Endpoint');
    await userEvent.click(createButton);

    await waitFor(() => {
      expect(screen.getByPlaceholderText('e.g., us-west-2')).toBeInTheDocument();
    });

    const cancelButton = screen.getByText('Cancel');
    await userEvent.click(cancelButton);

    await waitFor(() => {
      expect(screen.queryByPlaceholderText('e.g., us-west-2')).not.toBeInTheDocument();
    });
  });

  it('submits endpoint creation form with all required fields', async () => {

    render(
      <QueryClientProvider client={queryClient}>
        <EndpointsPage />
      </QueryClientProvider>
    );

    const createButton = screen.getByText('Create Endpoint');
    await userEvent.click(createButton);

    const regionInput = screen.getByPlaceholderText('e.g., us-west-2');
    const nameInput = screen.getByPlaceholderText('e.g., primary-node');
    const engineInput = screen.getByPlaceholderText('http://engine.local:8080');
    const targetInput = screen.getByPlaceholderText('node.example.com');

    await userEvent.type(regionInput, 'ap-southeast-1');
    await userEvent.type(nameInput, 'asia-node');
    await userEvent.type(engineInput, 'http://asia-engine:8080');
    await userEvent.type(targetInput, 'asia.example.com');

    const submitButton = screen.getByRole('button', { name: /Create/ });
    await userEvent.click(submitButton);

    await waitFor(() => {
      expect(c2cApi.createEndpoint).toHaveBeenCalledWith({
        region: 'ap-southeast-1',
        name: 'asia-node',
        engine_url: 'http://asia-engine:8080',
        target: 'asia.example.com',
      });
    });
  });

  it('submits endpoint creation form with optional api_key', async () => {

    render(
      <QueryClientProvider client={queryClient}>
        <EndpointsPage />
      </QueryClientProvider>
    );

    const createButton = screen.getByText('Create Endpoint');
    await userEvent.click(createButton);

    const regionInput = screen.getByPlaceholderText('e.g., us-west-2');
    const nameInput = screen.getByPlaceholderText('e.g., primary-node');
    const engineInput = screen.getByPlaceholderText('http://engine.local:8080');
    const targetInput = screen.getByPlaceholderText('node.example.com');
    const apiKeyInput = screen.getByPlaceholderText('auto-generated if empty');

    await userEvent.type(regionInput, 'us-east-1');
    await userEvent.type(nameInput, 'secure-node');
    await userEvent.type(engineInput, 'http://secure-engine:8080');
    await userEvent.type(targetInput, 'secure.example.com');
    await userEvent.type(apiKeyInput, 'secret-key-123');

    const submitButton = screen.getByRole('button', { name: /Create/ });
    await userEvent.click(submitButton);

    await waitFor(() => {
      expect(c2cApi.createEndpoint).toHaveBeenCalledWith({
        region: 'us-east-1',
        name: 'secure-node',
        engine_url: 'http://secure-engine:8080',
        target: 'secure.example.com',
        api_key: 'secret-key-123',
      });
    });
  });

  it('deletes endpoint when admin clicks delete', async () => {

    render(
      <QueryClientProvider client={queryClient}>
        <EndpointsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('node-1')).toBeInTheDocument();
    });

    const deleteButtons = screen.getAllByLabelText(/Delete endpoint/);
    await userEvent.click(deleteButtons[0]!);

    await waitFor(() => {
      expect(c2cApi.deleteEndpoint).toHaveBeenCalledWith('ep-1');
    });
  });

  it('hides delete actions for viewers', async () => {
    mockUseRole.mockReturnValue({ canWrite: () => false });

    render(
      <QueryClientProvider client={queryClient}>
        <EndpointsPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('node-1')).toBeInTheDocument();
    });

    expect(screen.queryByLabelText(/Delete endpoint/)).not.toBeInTheDocument();
  });
});
