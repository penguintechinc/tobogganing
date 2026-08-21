import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BlocklistPage } from './BlocklistPage';
import * as threatintelApi from '../../api/threatintel';

// Partial mock: preserve real constant exports (IOC_TYPES) via
// requireActual — full automock reduces `as const` array exports to `[]`,
// which breaks the page's default-value + <option> rendering logic.
jest.mock('../../api/threatintel', () => ({
  ...jest.requireActual('../../api/threatintel'),
  listBlocklist: jest.fn(),
  addBlocklistEntry: jest.fn(),
  deleteBlocklistEntry: jest.fn(),
}));
const mockedApi = threatintelApi as jest.Mocked<typeof threatintelApi>;

const mockEntries: threatintelApi.BlocklistEntry[] = [
  {
    id: 'e1',
    indicator_type: 'domain',
    value: 'malicious.example.com',
    source: 'manual',
    confidence: 100,
    active: true,
    created_at: '2026-08-01T00:00:00Z',
    updated_at: '2026-08-01T00:00:00Z',
  },
];

describe('BlocklistPage', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    jest.clearAllMocks();
    mockedApi.listBlocklist.mockResolvedValue(mockEntries);
    mockedApi.deleteBlocklistEntry.mockResolvedValue({
      message: 'Blocklist entry removed successfully',
      meta: { version: 1, timestamp: '2026-08-20T09:00:00Z' },
    });
    mockedApi.addBlocklistEntry.mockResolvedValue(mockEntries[0]!);
  });

  const renderPage = () =>
    render(
      <QueryClientProvider client={queryClient}>
        <BlocklistPage />
      </QueryClientProvider>
    );

  it('renders the page title', () => {
    renderPage();
    expect(screen.getByText('Blocklist')).toBeInTheDocument();
  });

  it('renders entry rows', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('malicious.example.com')).toBeInTheDocument();
    });
  });

  it('shows error state on fetch failure', async () => {
    mockedApi.listBlocklist.mockRejectedValue(new Error('Failed to fetch'));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Error loading data')).toBeInTheDocument();
    });
  });

  it('re-queries with the type filter applied', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('malicious.example.com')).toBeInTheDocument());

    fireEvent.change(screen.getByLabelText('Type'), { target: { value: 'ip' } });

    await waitFor(() => {
      expect(mockedApi.listBlocklist).toHaveBeenCalledWith({ indicator_type: 'ip' });
    });
  });

  it('re-queries with the source filter applied', async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(screen.getByText('malicious.example.com')).toBeInTheDocument());

    await user.type(screen.getByLabelText('Source'), 'misp');

    await waitFor(() => {
      expect(mockedApi.listBlocklist).toHaveBeenCalledWith({ source: 'misp' });
    });
  });

  it('adds an entry via the add-entry modal', async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(screen.getByText('malicious.example.com')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('Add blocklist entry'));
    await user.type(screen.getByLabelText('Value'), 'evil.example.com');
    fireEvent.click(screen.getByText('Save'));

    await waitFor(() => {
      expect(mockedApi.addBlocklistEntry).toHaveBeenCalledWith({
        indicator_type: 'ip',
        value: 'evil.example.com',
        source: 'manual',
        confidence: 100,
      });
    });
  });

  it('deletes an entry after confirmation', async () => {
    window.confirm = jest.fn(() => true);
    renderPage();
    await waitFor(() => expect(screen.getByText('malicious.example.com')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('Delete blocklist entry malicious.example.com'));

    await waitFor(() => {
      expect(mockedApi.deleteBlocklistEntry).toHaveBeenCalledWith('e1');
    });
  });
});
