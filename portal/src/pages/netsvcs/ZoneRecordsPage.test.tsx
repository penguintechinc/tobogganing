import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ZoneRecordsPage } from './ZoneRecordsPage';
import * as netsvcsApi from '../../api/netsvcs';

jest.mock('../../api/netsvcs');
const mockedApi = netsvcsApi as jest.Mocked<typeof netsvcsApi>;

const mockRecords: netsvcsApi.DnsRecord[] = [
  {
    id: 'rec-1',
    name: 'www',
    type: 'A',
    value: '1.2.3.4',
    ttl: 300,
    created_at: '2026-08-01T00:00:00Z',
    priority: null,
    weight: null,
    port: null,
  },
  {
    id: 'rec-2',
    name: '@',
    type: 'MX',
    value: 'mail.example.com',
    ttl: 3600,
    created_at: '2026-08-02T00:00:00Z',
    priority: 10,
    weight: null,
    port: null,
  },
];

describe('ZoneRecordsPage', () => {
  let queryClient: QueryClient;
  const onClose = jest.fn();

  beforeEach(() => {
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    jest.clearAllMocks();
    mockedApi.listRecords.mockResolvedValue(mockRecords);
    mockedApi.createRecord.mockResolvedValue(mockRecords[0] as netsvcsApi.DnsRecord);
    mockedApi.updateRecord.mockResolvedValue(mockRecords[0] as netsvcsApi.DnsRecord);
    mockedApi.deleteRecord.mockResolvedValue({
      message: 'Record deleted successfully',
      meta: { version: 1, timestamp: '2026-08-01T00:00:00Z' },
    });
  });

  const renderPage = () =>
    render(
      <QueryClientProvider client={queryClient}>
        <ZoneRecordsPage zoneId="zone-1" zoneName="example.com" onClose={onClose} />
      </QueryClientProvider>
    );

  it('renders the zone name header', async () => {
    renderPage();
    expect(screen.getByText('Records: example.com')).toBeInTheDocument();
  });

  it('renders records table with data', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('www')).toBeInTheDocument();
      expect(screen.getByText('mail.example.com')).toBeInTheDocument();
    });
  });

  it('fetches records for the given zone id', async () => {
    renderPage();
    await waitFor(() => {
      expect(mockedApi.listRecords).toHaveBeenCalledWith('zone-1');
    });
  });

  it('calls onClose when the close button is clicked', () => {
    renderPage();
    fireEvent.click(screen.getByLabelText('Close records'));
    expect(onClose).toHaveBeenCalled();
  });

  it('opens the create modal', async () => {
    renderPage();
    fireEvent.click(screen.getByLabelText('Add new record'));
    await waitFor(() => {
      expect(screen.getByRole('heading', { name: 'Add Record' })).toBeInTheDocument();
    });
  });

  it('creates a new A record', async () => {
    renderPage();
    fireEvent.click(screen.getByLabelText('Add new record'));

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Add Record' })).toBeInTheDocument()
    );

    fireEvent.change(screen.getByPlaceholderText('www'), { target: { value: 'api' } });
    fireEvent.change(screen.getByPlaceholderText('1.2.3.4'), { target: { value: '5.6.7.8' } });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => {
      expect(mockedApi.createRecord).toHaveBeenCalledWith('zone-1', {
        name: 'api',
        type: 'A',
        value: '5.6.7.8',
        ttl: 300,
        priority: null,
        weight: null,
        port: null,
      });
    });
  });

  it('shows priority/weight/port fields for SRV records', async () => {
    renderPage();
    fireEvent.click(screen.getByLabelText('Add new record'));

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Add Record' })).toBeInTheDocument()
    );
    fireEvent.change(screen.getByDisplayValue('A'), { target: { value: 'SRV' } });

    await waitFor(() => {
      expect(screen.getByText('Weight')).toBeInTheDocument();
      expect(screen.getByText('Port')).toBeInTheDocument();
    });
  });

  it('validates required fields before saving', async () => {
    const alertSpy = jest.spyOn(window, 'alert').mockImplementation();
    renderPage();
    fireEvent.click(screen.getByLabelText('Add new record'));

    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Add Record' })).toBeInTheDocument()
    );
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('Record name and value are required');
    });
    alertSpy.mockRestore();
  });

  it('opens the edit modal with existing values', async () => {
    renderPage();
    await waitFor(() => expect(screen.getAllByLabelText(/Edit record/).length).toBeGreaterThan(0));

    fireEvent.click(screen.getAllByLabelText(/Edit record/)[0]!);

    await waitFor(() => {
      expect(screen.getByText('Edit Record')).toBeInTheDocument();
      expect(screen.getByDisplayValue('www')).toBeInTheDocument();
    });
  });

  it('saves an edited SRV record via updateRecord', async () => {
    mockedApi.listRecords.mockResolvedValue([
      {
        id: 'rec-3',
        name: '_sip._tcp',
        type: 'SRV',
        value: 'sip.example.com',
        ttl: 300,
        created_at: '2026-08-03T00:00:00Z',
        priority: 10,
        weight: 5,
        port: 5060,
      },
    ]);
    renderPage();

    await waitFor(() => expect(screen.getAllByLabelText(/Edit record/).length).toBeGreaterThan(0));
    fireEvent.click(screen.getAllByLabelText(/Edit record/)[0]!);

    await waitFor(() => expect(screen.getByText('Edit Record')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText('TTL (seconds)'), { target: { value: '600' } });
    fireEvent.change(screen.getByLabelText('Priority'), { target: { value: '20' } });
    fireEvent.change(screen.getByLabelText('Weight'), { target: { value: '15' } });
    fireEvent.change(screen.getByLabelText('Port'), { target: { value: '5061' } });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => {
      expect(mockedApi.updateRecord).toHaveBeenCalledWith('zone-1', 'rec-3', {
        name: '_sip._tcp',
        type: 'SRV',
        value: 'sip.example.com',
        ttl: 600,
        priority: 20,
        weight: 15,
        port: 5061,
      });
    });
  });

  it('alerts when saving a record fails', async () => {
    const alertSpy = jest.spyOn(window, 'alert').mockImplementation();
    mockedApi.createRecord.mockRejectedValue(new Error('boom'));
    renderPage();

    fireEvent.click(screen.getByLabelText('Add new record'));
    await waitFor(() =>
      expect(screen.getByRole('heading', { name: 'Add Record' })).toBeInTheDocument()
    );

    fireEvent.change(screen.getByPlaceholderText('www'), { target: { value: 'fail' } });
    fireEvent.change(screen.getByPlaceholderText('1.2.3.4'), { target: { value: '9.9.9.9' } });
    fireEvent.click(screen.getByRole('button', { name: /save/i }));

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('Failed to save record');
    });
    alertSpy.mockRestore();
  });

  it('alerts when deleting a record fails', async () => {
    const alertSpy = jest.spyOn(window, 'alert').mockImplementation();
    window.confirm = jest.fn(() => true);
    mockedApi.deleteRecord.mockRejectedValue(new Error('boom'));
    renderPage();

    await waitFor(() =>
      expect(screen.getAllByLabelText(/Delete record/).length).toBeGreaterThan(0)
    );
    fireEvent.click(screen.getAllByLabelText(/Delete record/)[0]!);

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('Failed to delete record');
    });
    alertSpy.mockRestore();
  });

  it('retries the records query on error', async () => {
    mockedApi.listRecords.mockRejectedValue(new Error('Failed to fetch'));
    renderPage();

    await waitFor(() => expect(screen.getByText('Error loading data')).toBeInTheDocument());

    mockedApi.listRecords.mockResolvedValue(mockRecords);
    fireEvent.click(screen.getByText('Retry'));

    await waitFor(() => {
      expect(mockedApi.listRecords).toHaveBeenCalledTimes(2);
    });
  });

  it('deletes a record after confirmation', async () => {
    window.confirm = jest.fn(() => true);
    renderPage();

    await waitFor(() =>
      expect(screen.getAllByLabelText(/Delete record/).length).toBeGreaterThan(0)
    );
    fireEvent.click(screen.getAllByLabelText(/Delete record/)[0]!);

    await waitFor(() => {
      expect(mockedApi.deleteRecord).toHaveBeenCalledWith('zone-1', 'rec-1');
    });
  });

  it('does not delete a record when confirmation is declined', async () => {
    window.confirm = jest.fn(() => false);
    renderPage();

    await waitFor(() =>
      expect(screen.getAllByLabelText(/Delete record/).length).toBeGreaterThan(0)
    );
    fireEvent.click(screen.getAllByLabelText(/Delete record/)[0]!);

    expect(mockedApi.deleteRecord).not.toHaveBeenCalled();
  });

  it('shows error state on fetch failure', async () => {
    mockedApi.listRecords.mockRejectedValue(new Error('Failed to fetch'));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Error loading data')).toBeInTheDocument();
    });
  });
});
