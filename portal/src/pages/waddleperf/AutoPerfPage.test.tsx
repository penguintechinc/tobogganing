import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { AutoPerfPage } from './AutoPerfPage';
import * as wpcOps from '../../api/wpcOps';
import { useRole } from '../../hooks/useRole';

jest.mock('../../api/wpcOps');
jest.mock('../../hooks/useRole', () => ({ useRole: jest.fn() }));

const mockUseRole = useRole as jest.Mock;

const createQueryClient = () =>
  new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });

const mockPolicies: wpcOps.AutoPerfPolicy[] = [
  {
    id: 'policy-1',
    tenant: 'tenant-1',
    name: 'Production Monitor',
    device_id: 'dev-1',
    target: '192.168.1.1',
    t1_interval_seconds: 300,
    t2_interval_seconds: 120,
    t3_interval_seconds: 60,
    deescalate_after_clean: 3,
    enabled: true,
    created_at: '2026-07-15T00:00:00Z',
  },
];

const mockState: wpcOps.AutoPerfState = {
  current_tier: 'T1',
  clean_cycles: 2,
  escalated_at: null,
};

const mockStateWithEscalation: wpcOps.AutoPerfState = {
  current_tier: 'T3',
  clean_cycles: 0,
  escalated_at: '2026-07-15T12:00:00Z',
};

describe('AutoPerfPage', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    (wpcOps.listAutoPerfPolicies as jest.Mock).mockResolvedValue(mockPolicies);
    (wpcOps.getAutoPerfPolicyState as jest.Mock).mockResolvedValue(mockState);
    mockUseRole.mockReturnValue({ role: 'admin', canWrite: () => true });
  });

  it('renders the page title', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoPerfPage />
      </QueryClientProvider>
    );

    expect(screen.getByText('AutoPerf')).toBeInTheDocument();
  });

  it('loads and displays policies', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoPerfPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Production Monitor')).toBeInTheDocument();
      expect(screen.getByText('192.168.1.1')).toBeInTheDocument();
    });
  });

  it('shows Create Policy button when canWrite is true', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoPerfPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Create Policy')).toBeInTheDocument();
    });
  });

  it('hides Create Policy button when canWrite is false', async () => {
    mockUseRole.mockReturnValue({ role: 'viewer', canWrite: () => false });

    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoPerfPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.queryByText('Create Policy')).not.toBeInTheDocument();
    });
  });

  it('displays state and delete actions for admin', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoPerfPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      const stateButtons = screen.getAllByText('State');
      expect(stateButtons.length).toBeGreaterThan(0);
      expect(screen.getByText('Delete')).toBeInTheDocument();
    });
  });

  it('shows View button instead of Delete for viewers', async () => {
    mockUseRole.mockReturnValue({ role: 'viewer', canWrite: () => false });

    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoPerfPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('View')).toBeInTheDocument();
      expect(screen.queryByText('Delete')).not.toBeInTheDocument();
    });
  });

  it('toggles form visibility', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoPerfPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Create Policy')).toBeInTheDocument();
    });

    const createBtn = screen.getByText('Create Policy');
    await userEvent.click(createBtn);

    await waitFor(() => {
      expect(screen.getByDisplayValue('300')).toBeInTheDocument();
    });

    const cancelBtn = screen.getByText('Cancel');
    await userEvent.click(cancelBtn);

    await waitFor(() => {
      expect(screen.queryByDisplayValue('300')).not.toBeInTheDocument();
    });
  });

  it('submits create form with all fields', async () => {
    (wpcOps.createAutoPerfPolicy as jest.Mock).mockResolvedValue({
      id: 'policy-2',
      ...mockPolicies[0],
      name: 'New Policy',
    });

    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoPerfPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Create Policy')).toBeInTheDocument();
    });

    const createBtn = screen.getByText('Create Policy');
    await userEvent.click(createBtn);

    const nameInput = screen.getByPlaceholderText('Policy name');
    const deviceInput = screen.getByPlaceholderText('Device ID');
    const targetInput = screen.getByPlaceholderText('Target IP/hostname');

    await userEvent.type(nameInput, 'New Policy');
    await userEvent.type(deviceInput, 'dev-2');
    await userEvent.type(targetInput, '192.168.1.2');

    const submitBtn = screen.getByRole('button', { name: 'Create' });
    await userEvent.click(submitBtn);

    await waitFor(() => {
      expect(wpcOps.createAutoPerfPolicy).toHaveBeenCalledWith({
        name: 'New Policy',
        device_id: 'dev-2',
        target: '192.168.1.2',
        t1_interval_seconds: 300,
        t2_interval_seconds: 120,
        t3_interval_seconds: 60,
        deescalate_after_clean: 3,
      });
    });
  });

  it('shows tier badge for different tiers', async () => {
    (wpcOps.getAutoPerfPolicyState as jest.Mock).mockImplementation(() =>
      Promise.resolve({ current_tier: 'T2', clean_cycles: 1, escalated_at: null })
    );

    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoPerfPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Production Monitor')).toBeInTheDocument();
    });

    const stateButton = screen.getByText('State');
    await userEvent.click(stateButton);

    await waitFor(() => {
      expect(screen.getByText('T2')).toBeInTheDocument();
    });
  });

  it('displays escalated_at in state panel when present', async () => {
    (wpcOps.getAutoPerfPolicyState as jest.Mock).mockResolvedValue(mockStateWithEscalation);

    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoPerfPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Production Monitor')).toBeInTheDocument();
    });

    const stateButton = screen.getByText('State');
    await userEvent.click(stateButton);

    await waitFor(() => {
      expect(screen.getByText('Escalated:')).toBeInTheDocument();
    });
  });

  it('toggles expanded policy view', async () => {
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoPerfPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Production Monitor')).toBeInTheDocument();
    });

    const stateButton = screen.getByText('State');
    await userEvent.click(stateButton);

    await waitFor(() => {
      expect(screen.getByText('State for Production Monitor')).toBeInTheDocument();
    });

    const hideButton = screen.getByText('Hide');
    await userEvent.click(hideButton);

    await waitFor(() => {
      expect(screen.queryByText('State for Production Monitor')).not.toBeInTheDocument();
    });
  });

  it('calls delete mutation on delete button click', async () => {
    (wpcOps.deleteAutoPerfPolicy as jest.Mock).mockResolvedValue(undefined);

    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoPerfPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Production Monitor')).toBeInTheDocument();
    });

    const deleteButton = screen.getByText('Delete');
    await userEvent.click(deleteButton);

    await waitFor(() => {
      expect(wpcOps.deleteAutoPerfPolicy).toHaveBeenCalledWith('policy-1');
    });
  });

  it('displays empty state when no policies', async () => {
    (wpcOps.listAutoPerfPolicies as jest.Mock).mockResolvedValue([]);
    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoPerfPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('No data available')).toBeInTheDocument();
    });
  });

  it('displays loading state for state panel', async () => {
    (wpcOps.getAutoPerfPolicyState as jest.Mock).mockImplementation(
      () =>
        new Promise((resolve) => {
          setTimeout(() => resolve(mockState), 100);
        })
    );

    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoPerfPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Production Monitor')).toBeInTheDocument();
    });

    const stateButton = screen.getByText('State');
    await userEvent.click(stateButton);

    expect(screen.getByText('Loading state...')).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.queryByText('Loading state...')).not.toBeInTheDocument();
    });
  });

  it('handles state panel with no state available', async () => {
    (wpcOps.getAutoPerfPolicyState as jest.Mock).mockResolvedValue(null);

    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoPerfPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Production Monitor')).toBeInTheDocument();
    });

    const stateButton = screen.getByText('State');
    await userEvent.click(stateButton);

    await waitFor(() => {
      expect(screen.getByText('No state available')).toBeInTheDocument();
    });
  });

  it('uses custom tier colors for T3', async () => {
    (wpcOps.getAutoPerfPolicyState as jest.Mock).mockResolvedValue({
      current_tier: 'T3',
      clean_cycles: 0,
      escalated_at: null,
    });

    const queryClient = createQueryClient();
    render(
      <QueryClientProvider client={queryClient}>
        <AutoPerfPage />
      </QueryClientProvider>
    );

    await waitFor(() => {
      expect(screen.getByText('Production Monitor')).toBeInTheDocument();
    });

    const stateButton = screen.getByText('State');
    await userEvent.click(stateButton);

    await waitFor(() => {
      const t3Badge = screen.getByText('T3');
      expect(t3Badge).toHaveClass('bg-red-900');
      expect(t3Badge).toHaveClass('text-red-200');
    });
  });
});
