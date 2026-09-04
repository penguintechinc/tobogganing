import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BlockRoutingConfig } from './BlockRoutingConfig';
import * as saseApi from '../../api/sase';

// Mock the API
jest.mock('../../api/sase');
const mockedSaseApi = saseApi as jest.Mocked<typeof saseApi>;

describe('BlockRoutingConfig', () => {
  let queryClient: QueryClient;

  const mockPages: saseApi.BlockPage[] = [
    {
      id: 'page-1',
      tenant: 'tenant-1',
      name: 'Malware Block Page',
      markdown: '# Malware Detected',
      status: 'live',
      version: 1,
      created_by: 'user-1',
      updated_by: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
    {
      id: 'page-2',
      tenant: 'tenant-1',
      name: 'Gambling Block Page',
      markdown: '# Gambling Blocked',
      status: 'live',
      version: 1,
      created_by: 'user-1',
      updated_by: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
  ];

  const mockRoutes: saseApi.BlockRoute[] = [
    {
      id: 'route-1',
      tenant: 'tenant-1',
      source_type: 'web-category:malware',
      destination_kind: 'page',
      page_id: 'page-1',
      external_url: null,
      created_at: new Date().toISOString(),
      created_by: 'user-1',
      updated_by: null,
      ticket: null,
      notes: null,
      expiry: null,
      review_date: null,
      scope: null,
      risk: null,
    },
    {
      id: 'route-2',
      tenant: 'tenant-1',
      source_type: 'web-category:gambling',
      destination_kind: 'external',
      page_id: null,
      external_url: 'https://blocked.example.com',
      created_at: new Date().toISOString(),
      created_by: 'user-1',
      updated_by: null,
      ticket: 'TICKET-123',
      notes: 'Redirect to external block page',
      expiry: null,
      review_date: null,
      scope: 'tenant',
      risk: 'low',
    },
  ];

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    // Clear all mocks from previous tests
    jest.clearAllMocks();

    mockedSaseApi.listBlockPages.mockResolvedValue(mockPages);
    mockedSaseApi.listBlockRoutes.mockResolvedValue(mockRoutes);
    mockedSaseApi.upsertBlockRoutes.mockResolvedValue(mockRoutes);
  });

  const renderComponent = () => {
    return render(
      <QueryClientProvider client={queryClient}>
        <BlockRoutingConfig />
      </QueryClientProvider>
    );
  };

  it('renders the config page with title', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Block Routing Config')).toBeInTheDocument();
    });
  });

  it('displays routes table with all columns', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('Source Type')).toBeInTheDocument();
      expect(screen.getByText('Destination')).toBeInTheDocument();
      expect(screen.getByText('Kind')).toBeInTheDocument();
      expect(screen.getByText('Actions')).toBeInTheDocument();
    });
  });

  it('displays route rows in table', async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('web-category:malware')).toBeInTheDocument();
      expect(screen.getByText('web-category:gambling')).toBeInTheDocument();
      expect(screen.getByText('Malware Block Page')).toBeInTheDocument();
      expect(screen.getByText('https://blocked.example.com')).toBeInTheDocument();
    });
  });

  it('shows page destination kind badge', async () => {
    renderComponent();

    await waitFor(() => {
      const badges = screen.getAllByText('page');
      expect(badges.length).toBeGreaterThan(0);
    });
  });

  it('shows external destination kind badge', async () => {
    renderComponent();

    await waitFor(() => {
      const badges = screen.getAllByText('external');
      expect(badges.length).toBeGreaterThan(0);
    });
  });

  it('opens modal when Add Route button clicked', async () => {
    renderComponent();

    const addButton = screen.getByLabelText('Add new route');
    expect(addButton).toBeInTheDocument();
    fireEvent.click(addButton);

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /add route/i })).toBeInTheDocument();
      expect(screen.getByPlaceholderText('e.g., web-category:gambling')).toBeInTheDocument();
    });
  });

  it('opens edit modal when edit button clicked', async () => {
    renderComponent();

    await waitFor(() => {
      const editButtons = screen.getAllByLabelText(/Edit route/);
      expect(editButtons.length).toBeGreaterThan(0);
      fireEvent.click(editButtons[0]!);
    });

    await waitFor(() => {
      expect(screen.getByText('Edit Route')).toBeInTheDocument();
    });
  });

  it('creates a new page route', async () => {
    renderComponent();

    // Open add modal
    fireEvent.click(screen.getByLabelText('Add new route'));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /add route/i })).toBeInTheDocument();
    });

    // Fill in source type
    const sourceInputs = screen.getAllByPlaceholderText('e.g., web-category:gambling');
    expect(sourceInputs.length).toBeGreaterThan(0);
    fireEvent.change(sourceInputs[0]!, { target: { value: 'custom-rule:phishing' } });

    // Select a page
    const pageSelects = screen.getAllByDisplayValue('-- Select a page --');
    expect(pageSelects.length).toBeGreaterThan(0);
    fireEvent.change(pageSelects[0]!, { target: { value: 'page-1' } });

    // Save
    const saveButton = screen.getByRole('button', { name: /save/i });
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(mockedSaseApi.upsertBlockRoutes).toHaveBeenCalled();
      const calls = mockedSaseApi.upsertBlockRoutes.mock.calls;
      expect(calls.length).toBeGreaterThan(0);
      const callArgs = calls[0]![0]!;
      expect(
        callArgs.some(
          (r) => r.source_type === 'custom-rule:phishing' && r.destination_kind === 'page'
        )
      ).toBe(true);
    });
  });

  it('creates a new external route', async () => {
    renderComponent();

    // Open add modal
    fireEvent.click(screen.getByLabelText('Add new route'));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /add route/i })).toBeInTheDocument();
    });

    // Fill in source type
    const sourceInputs = screen.getAllByPlaceholderText('e.g., web-category:gambling');
    expect(sourceInputs.length).toBeGreaterThan(0);
    fireEvent.change(sourceInputs[0]!, { target: { value: 'soft-block' } });

    // Switch to external
    const destSelects = screen.getAllByDisplayValue('Page');
    expect(destSelects.length).toBeGreaterThan(0);
    fireEvent.change(destSelects[0]!, { target: { value: 'external' } });

    await waitFor(() => {
      expect(screen.getByPlaceholderText('https://example.com/block')).toBeInTheDocument();
    });

    // Enter external URL
    const urlInputs = screen.getAllByPlaceholderText('https://example.com/block');
    expect(urlInputs.length).toBeGreaterThan(0);
    fireEvent.change(urlInputs[0]!, { target: { value: 'https://external-block.example.com' } });

    // Save
    const saveButton = screen.getByRole('button', { name: /save/i });
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(mockedSaseApi.upsertBlockRoutes).toHaveBeenCalled();
      const calls = mockedSaseApi.upsertBlockRoutes.mock.calls;
      expect(calls.length).toBeGreaterThan(0);
      const callArgs = calls[0]![0]!;
      expect(
        callArgs.some((r) => r.source_type === 'soft-block' && r.destination_kind === 'external')
      ).toBe(true);
    });
  });

  it('adds governance metadata', async () => {
    renderComponent();

    // Open add modal
    fireEvent.click(screen.getByLabelText('Add new route'));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /add route/i })).toBeInTheDocument();
    });

    // Fill in source type
    const sourceInputs = screen.getAllByPlaceholderText('e.g., web-category:gambling');
    expect(sourceInputs.length).toBeGreaterThan(0);
    fireEvent.change(sourceInputs[0]!, { target: { value: 'web-category:violence' } });

    // Select a page for the route to be valid
    const pageSelects = screen.getAllByDisplayValue('-- Select a page --');
    expect(pageSelects.length).toBeGreaterThan(0);
    fireEvent.change(pageSelects[0]!, { target: { value: 'page-1' } });

    // Fill in metadata
    const ticketInputs = screen.getAllByPlaceholderText('Ticket ID');
    expect(ticketInputs.length).toBeGreaterThan(0);
    fireEvent.change(ticketInputs[0]!, { target: { value: 'SEC-456' } });

    const noteInputs = screen.getAllByPlaceholderText('Notes');
    expect(noteInputs.length).toBeGreaterThan(0);
    fireEvent.change(noteInputs[0]!, { target: { value: 'Violence content blocking' } });

    const scopeSelect = screen.getAllByDisplayValue('-- Scope --');
    expect(scopeSelect.length).toBeGreaterThan(0);
    fireEvent.change(scopeSelect[0]!, { target: { value: 'tenant' } });

    const riskSelect = screen.getAllByDisplayValue('-- Risk --');
    expect(riskSelect.length).toBeGreaterThan(0);
    fireEvent.change(riskSelect[0]!, { target: { value: 'high' } });

    // Save
    const saveButton = screen.getByRole('button', { name: /save/i });
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(mockedSaseApi.upsertBlockRoutes).toHaveBeenCalled();
      const calls = mockedSaseApi.upsertBlockRoutes.mock.calls;
      expect(calls.length).toBeGreaterThan(0);
      const callArgs = calls[0]![0]!;
      const newRoute = callArgs.find((r) => r.source_type === 'web-category:violence');
      expect(newRoute?.metadata?.ticket).toBe('SEC-456');
      expect(newRoute?.metadata?.notes).toBe('Violence content blocking');
      expect(newRoute?.metadata?.scope).toBe('tenant');
      expect(newRoute?.metadata?.risk).toBe('high');
    });
  });

  it('validates required fields before saving', async () => {
    const alertSpy = jest.spyOn(window, 'alert').mockImplementation();

    renderComponent();

    fireEvent.click(screen.getByLabelText('Add new route'));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /add route/i })).toBeInTheDocument();
    });

    // Try to save without source type
    const saveButton = screen.getByRole('button', { name: /save/i });
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('Source type is required');
    });

    alertSpy.mockRestore();
  });

  it('deletes a route', async () => {
    renderComponent();

    await waitFor(() => {
      const deleteButtons = screen.getAllByLabelText(/Delete route/);
      expect(deleteButtons.length).toBeGreaterThan(0);
    });

    // Mock confirm
    window.confirm = jest.fn(() => true);

    const deleteButtons = screen.getAllByLabelText(/Delete route/);
    expect(deleteButtons.length).toBeGreaterThan(0);
    fireEvent.click(deleteButtons[0]!);

    await waitFor(() => {
      expect(mockedSaseApi.upsertBlockRoutes).toHaveBeenCalled();
    });
  });

  it('shows empty state when no routes', async () => {
    mockedSaseApi.listBlockRoutes.mockResolvedValue([]);

    renderComponent();

    await waitFor(() => {
      expect(screen.getByText('No routes configured. Add one to get started.')).toBeInTheDocument();
    });
  });

  it('console logs route operations', async () => {
    const consoleSpy = jest.spyOn(console, 'log').mockImplementation();

    renderComponent();

    await waitFor(() => {
      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining('[BlockRoutingConfig]'),
        expect.any(Object)
      );
    });

    consoleSpy.mockRestore();
  });

  it('displays route metadata in edit modal', async () => {
    renderComponent();

    await waitFor(() => {
      const editButtons = screen.getAllByLabelText(/Edit route/);
      expect(editButtons.length).toBeGreaterThan(1);
      fireEvent.click(editButtons[1]!); // Edit the gambling route with metadata
    });

    await waitFor(() => {
      expect(screen.getByDisplayValue('TICKET-123')).toBeInTheDocument();
      expect(screen.getByDisplayValue('Redirect to external block page')).toBeInTheDocument();
    });
  });

  it('validates page selection is required for page destination', async () => {
    const alertSpy = jest.spyOn(window, 'alert').mockImplementation();

    renderComponent();

    fireEvent.click(screen.getByLabelText('Add new route'));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /add route/i })).toBeInTheDocument();
    });

    const sourceInputs = screen.getAllByPlaceholderText('e.g., web-category:gambling');
    fireEvent.change(sourceInputs[0]!, { target: { value: 'custom-rule:no-page' } });

    // Leave page selection empty, attempt save
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('Page selection is required');
    });
    expect(mockedSaseApi.upsertBlockRoutes).not.toHaveBeenCalled();

    alertSpy.mockRestore();
  });

  it('validates external URL is required for external destination', async () => {
    const alertSpy = jest.spyOn(window, 'alert').mockImplementation();

    renderComponent();

    fireEvent.click(screen.getByLabelText('Add new route'));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /add route/i })).toBeInTheDocument();
    });

    const sourceInputs = screen.getAllByPlaceholderText('e.g., web-category:gambling');
    fireEvent.change(sourceInputs[0]!, { target: { value: 'custom-rule:no-url' } });

    const destSelects = screen.getAllByDisplayValue('Page');
    fireEvent.change(destSelects[0]!, { target: { value: 'external' } });

    await waitFor(() => {
      expect(screen.getByPlaceholderText('https://example.com/block')).toBeInTheDocument();
    });

    // Leave external URL empty, attempt save
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('External URL is required');
    });
    expect(mockedSaseApi.upsertBlockRoutes).not.toHaveBeenCalled();

    alertSpy.mockRestore();
  });

  it('excludes the original entry when saving an edited route', async () => {
    renderComponent();

    await waitFor(() => {
      const editButtons = screen.getAllByLabelText(/Edit route/);
      expect(editButtons.length).toBeGreaterThan(0);
      fireEvent.click(editButtons[0]!); // Edit route-1 (web-category:malware)
    });

    await waitFor(() => {
      expect(screen.getByText('Edit Route')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => {
      expect(mockedSaseApi.upsertBlockRoutes).toHaveBeenCalled();
      const calls = mockedSaseApi.upsertBlockRoutes.mock.calls;
      const callArgs = calls[0]![0]!;
      // Only one entry for web-category:malware should be present (no duplicate)
      const matches = callArgs.filter((r) => r.source_type === 'web-category:malware');
      expect(matches.length).toBe(1);
    });
  });

  it('shows an alert when saving routes fails', async () => {
    const alertSpy = jest.spyOn(window, 'alert').mockImplementation();
    const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation();
    mockedSaseApi.upsertBlockRoutes.mockRejectedValue(new Error('network error'));

    renderComponent();

    fireEvent.click(screen.getByLabelText('Add new route'));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /add route/i })).toBeInTheDocument();
    });

    const sourceInputs = screen.getAllByPlaceholderText('e.g., web-category:gambling');
    fireEvent.change(sourceInputs[0]!, { target: { value: 'custom-rule:fails' } });

    const pageSelects = screen.getAllByDisplayValue('-- Select a page --');
    fireEvent.change(pageSelects[0]!, { target: { value: 'page-1' } });

    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('Failed to save routes');
    });
    expect(consoleErrorSpy).toHaveBeenCalledWith(
      expect.stringContaining('SaveRoutes error'),
      expect.any(Object)
    );

    alertSpy.mockRestore();
    consoleErrorSpy.mockRestore();
  });

  it('deletes a route leaving only routes with empty metadata', async () => {
    renderComponent();

    await waitFor(() => {
      const deleteButtons = screen.getAllByLabelText(/Delete route/);
      expect(deleteButtons.length).toBeGreaterThan(1);
    });

    window.confirm = jest.fn(() => true);

    // Delete route-2 (has metadata), leaving route-1 (all-null metadata) remaining
    const deleteButtons = screen.getAllByLabelText(/Delete route/);
    fireEvent.click(deleteButtons[1]!);

    await waitFor(() => {
      expect(mockedSaseApi.upsertBlockRoutes).toHaveBeenCalled();
      const calls = mockedSaseApi.upsertBlockRoutes.mock.calls;
      const callArgs = calls[0]![0]!;
      const remaining = callArgs.find((r) => r.source_type === 'web-category:malware');
      expect(remaining?.metadata).toBeUndefined();
    });
  });

  it('does not delete a route when confirm is cancelled', async () => {
    renderComponent();

    await waitFor(() => {
      const deleteButtons = screen.getAllByLabelText(/Delete route/);
      expect(deleteButtons.length).toBeGreaterThan(0);
    });

    window.confirm = jest.fn(() => false);

    const deleteButtons = screen.getAllByLabelText(/Delete route/);
    fireEvent.click(deleteButtons[0]!);

    expect(mockedSaseApi.upsertBlockRoutes).not.toHaveBeenCalled();
  });

  it('sets an expiry date and closes the modal via cancel', async () => {
    renderComponent();

    fireEvent.click(screen.getByLabelText('Add new route'));

    await waitFor(() => {
      expect(screen.getByRole('heading', { name: /add route/i })).toBeInTheDocument();
    });

    const container = screen.getByPlaceholderText('Ticket ID').closest('div');
    const expiryInput = container?.querySelector('input[type="date"]');
    expect(expiryInput).toBeInTheDocument();
    fireEvent.change(expiryInput as Element, { target: { value: '2026-12-31' } });
    expect((expiryInput as HTMLInputElement).value).toBe('2026-12-31');

    fireEvent.click(screen.getByRole('button', { name: /cancel/i }));

    await waitFor(() => {
      expect(screen.queryByRole('heading', { name: /add route/i })).not.toBeInTheDocument();
    });
  });
});
