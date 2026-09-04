import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ZonesPage } from './ZonesPage';
import * as netsvcsApi from '../../api/netsvcs';

jest.mock('../../api/netsvcs');
const mockedApi = netsvcsApi as jest.Mocked<typeof netsvcsApi>;

const mockZones: netsvcsApi.Zone[] = [
  {
    id: 'zone-1',
    name: 'example.com',
    visibility: 'public',
    description: 'Primary zone',
    created_at: '2026-08-01T00:00:00Z',
  },
  {
    id: 'zone-2',
    name: 'internal.example.com',
    visibility: 'private',
    description: null,
    created_at: '2026-08-02T00:00:00Z',
  },
];

describe('ZonesPage', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    jest.clearAllMocks();
    mockedApi.listZones.mockResolvedValue(mockZones);
    mockedApi.listRecords.mockResolvedValue([]);
    mockedApi.createZone.mockResolvedValue(mockZones[0] as netsvcsApi.Zone);
    mockedApi.updateZone.mockResolvedValue(mockZones[0] as netsvcsApi.Zone);
    mockedApi.deleteZone.mockResolvedValue({
      message: 'Zone deleted successfully',
      meta: { version: 1, timestamp: '2026-08-01T00:00:00Z' },
    });
  });

  const renderPage = () =>
    render(
      <QueryClientProvider client={queryClient}>
        <ZonesPage />
      </QueryClientProvider>
    );

  it('renders the page title', async () => {
    renderPage();
    expect(screen.getByText('Zones')).toBeInTheDocument();
  });

  it('renders zones table with data', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('example.com')).toBeInTheDocument();
      expect(screen.getByText('internal.example.com')).toBeInTheDocument();
    });
  });

  it('shows empty state when no zones', async () => {
    mockedApi.listZones.mockResolvedValue([]);
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('No data available')).toBeInTheDocument();
    });
  });

  it('shows error state on fetch failure', async () => {
    mockedApi.listZones.mockRejectedValue(new Error('Failed to fetch'));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Error loading data')).toBeInTheDocument();
    });
  });

  it('opens the create modal', async () => {
    renderPage();
    fireEvent.click(screen.getByLabelText('Add new zone'));
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Add Zone' })).toBeInTheDocument();
    });
  });

  it('creates a new zone', async () => {
    renderPage();
    fireEvent.click(screen.getByLabelText('Add new zone'));

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Add Zone' })).toBeInTheDocument()
    );

    fireEvent.change(screen.getByPlaceholderText('example.com'), {
      target: { value: 'new-zone.com' },
    });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => {
      expect(mockedApi.createZone).toHaveBeenCalledWith({
        name: 'new-zone.com',
        visibility: 'public',
        description: null,
      });
    });
  });

  it('validates zone name before saving', async () => {
    const alertSpy = jest.spyOn(window, 'alert').mockImplementation();
    renderPage();
    fireEvent.click(screen.getByLabelText('Add new zone'));

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Add Zone' })).toBeInTheDocument()
    );
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('Zone name is required');
    });
    alertSpy.mockRestore();
  });

  it('opens the edit modal with existing values', async () => {
    renderPage();
    await waitFor(() => expect(screen.getAllByLabelText(/Edit zone/).length).toBeGreaterThan(0));

    fireEvent.click(screen.getAllByLabelText(/Edit zone/)[0]!);

    await waitFor(() => {
      expect(screen.getByText('Edit Zone')).toBeInTheDocument();
      expect(screen.getByDisplayValue('example.com')).toBeInTheDocument();
    });
  });

  it('saves an edited zone via updateZone', async () => {
    renderPage();
    await waitFor(() => expect(screen.getAllByLabelText(/Edit zone/).length).toBeGreaterThan(0));

    fireEvent.click(screen.getAllByLabelText(/Edit zone/)[0]!);
    await waitFor(() => expect(screen.getByText('Edit Zone')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText('Visibility'), { target: { value: 'private' } });
    fireEvent.change(screen.getByLabelText('Description'), { target: { value: 'Updated desc' } });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => {
      expect(mockedApi.updateZone).toHaveBeenCalledWith('zone-1', {
        name: 'example.com',
        visibility: 'private',
        description: 'Updated desc',
      });
    });
  });

  it('alerts when saving a zone fails', async () => {
    const alertSpy = jest.spyOn(window, 'alert').mockImplementation();
    mockedApi.createZone.mockRejectedValue(new Error('boom'));
    renderPage();

    fireEvent.click(screen.getByLabelText('Add new zone'));
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Add Zone' })).toBeInTheDocument()
    );

    fireEvent.change(screen.getByPlaceholderText('example.com'), { target: { value: 'fail.com' } });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('Failed to save zone');
    });
    alertSpy.mockRestore();
  });

  it('alerts when deleting a zone fails', async () => {
    const alertSpy = jest.spyOn(window, 'alert').mockImplementation();
    window.confirm = jest.fn(() => true);
    mockedApi.deleteZone.mockRejectedValue(new Error('boom'));
    renderPage();

    await waitFor(() => expect(screen.getAllByLabelText(/Delete zone/).length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByLabelText(/Delete zone/)[0]!);

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('Failed to delete zone');
    });
    alertSpy.mockRestore();
  });

  it('collapses the drilldown when the expanded zone is deleted', async () => {
    const user = userEvent.setup();
    window.confirm = jest.fn(() => true);
    renderPage();

    const expandButton = await screen.findByText('example.com');
    await user.click(expandButton);
    await waitFor(() => expect(screen.getByText('Records: example.com')).toBeInTheDocument());

    fireEvent.click(screen.getAllByLabelText(/Delete zone/)[0]!);

    await waitFor(() => {
      expect(mockedApi.deleteZone).toHaveBeenCalledWith('zone-1');
      expect(screen.queryByText('Records: example.com')).not.toBeInTheDocument();
    });
  });

  it('retries the zones query on error', async () => {
    mockedApi.listZones.mockRejectedValue(new Error('Failed to fetch'));
    renderPage();

    await waitFor(() => expect(screen.getByText('Error loading data')).toBeInTheDocument());

    mockedApi.listZones.mockResolvedValue(mockZones);
    fireEvent.click(screen.getByText('Retry'));

    await waitFor(() => {
      expect(mockedApi.listZones).toHaveBeenCalledTimes(2);
    });
  });

  it('deletes a zone after confirmation', async () => {
    window.confirm = jest.fn(() => true);
    renderPage();

    await waitFor(() => expect(screen.getAllByLabelText(/Delete zone/).length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByLabelText(/Delete zone/)[0]!);

    await waitFor(() => {
      expect(mockedApi.deleteZone).toHaveBeenCalledWith('zone-1');
    });
  });

  it('does not delete a zone when confirmation is declined', async () => {
    window.confirm = jest.fn(() => false);
    renderPage();

    await waitFor(() => expect(screen.getAllByLabelText(/Delete zone/).length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByLabelText(/Delete zone/)[0]!);

    expect(mockedApi.deleteZone).not.toHaveBeenCalled();
  });

  it('expands a zone row to show records drilldown', async () => {
    const user = userEvent.setup();
    renderPage();

    const expandButton = await screen.findByText('example.com');
    await user.click(expandButton);

    await waitFor(() => {
      expect(screen.getByText('Records: example.com')).toBeInTheDocument();
    });
  });

  it('collapses the records drilldown when closed', async () => {
    const user = userEvent.setup();
    renderPage();

    const expandButton = await screen.findByText('example.com');
    await user.click(expandButton);

    await waitFor(() => expect(screen.getByText('Records: example.com')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('Close records'));

    await waitFor(() => {
      expect(screen.queryByText('Records: example.com')).not.toBeInTheDocument();
    });
  });

  it('closes the create/edit modal on cancel', async () => {
    renderPage();
    fireEvent.click(screen.getByLabelText('Add new zone'));

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Add Zone' })).toBeInTheDocument()
    );
    fireEvent.click(screen.getByText('Cancel'));

    await waitFor(() => {
      expect(screen.queryByRole('heading', { name: 'Add Zone' })).not.toBeInTheDocument();
    });
  });
});
