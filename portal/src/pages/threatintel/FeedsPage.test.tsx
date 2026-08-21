import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { FeedsPage } from './FeedsPage';
import * as threatintelApi from '../../api/threatintel';

// Partial mock: preserve real constant exports (FEED_SOURCE_TYPES) via
// requireActual — full automock reduces `as const` array exports to `[]`,
// which breaks the page's default-value + <option> rendering logic.
jest.mock('../../api/threatintel', () => ({
  ...jest.requireActual('../../api/threatintel'),
  listFeeds: jest.fn(),
  createFeed: jest.fn(),
  deleteFeed: jest.fn(),
  refreshFeed: jest.fn(),
}));
const mockedApi = threatintelApi as jest.Mocked<typeof threatintelApi>;

const mockFeeds: threatintelApi.FeedSource[] = [
  {
    id: 'f1',
    name: 'my-misp',
    source_type: 'misp',
    url: 'https://misp.example.com/export.json',
    enabled: true,
    last_refresh_at: '2026-08-20T09:00:00Z',
    last_refresh_status: 'completed',
    last_refresh_error: null,
    created_at: '2026-08-01T00:00:00Z',
  },
];

describe('FeedsPage', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    jest.clearAllMocks();
    mockedApi.listFeeds.mockResolvedValue(mockFeeds);
    mockedApi.deleteFeed.mockResolvedValue({
      message: 'Feed source deleted successfully',
      meta: { version: 1, timestamp: '2026-08-20T09:00:00Z' },
    });
    mockedApi.refreshFeed.mockResolvedValue({
      id: 'f1',
      status: 'completed',
      added: 5,
      updated: 1,
      errors: 0,
      meta: { version: 1, timestamp: '2026-08-20T09:00:00Z' },
    });
    mockedApi.createFeed.mockResolvedValue(mockFeeds[0]!);
  });

  const renderPage = () =>
    render(
      <QueryClientProvider client={queryClient}>
        <FeedsPage />
      </QueryClientProvider>
    );

  it('renders the page title', () => {
    renderPage();
    expect(screen.getByText('Feeds')).toBeInTheDocument();
  });

  it('renders feed rows', async () => {
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('my-misp')).toBeInTheDocument();
    });
  });

  it('shows error state on fetch failure', async () => {
    mockedApi.listFeeds.mockRejectedValue(new Error('Failed to fetch'));
    renderPage();
    await waitFor(() => {
      expect(screen.getByText('Error loading data')).toBeInTheDocument();
    });
  });

  it('creates a feed via the add-feed modal', async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(screen.getByText('my-misp')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('Add new feed source'));
    await user.type(screen.getByLabelText('Name'), 'new-feed');
    await user.type(screen.getByLabelText('URL'), 'https://feed.example.com/data.json');
    fireEvent.click(screen.getByText('Save'));

    await waitFor(() => {
      expect(mockedApi.createFeed).toHaveBeenCalledWith({
        name: 'new-feed',
        source_type: 'misp',
        url: 'https://feed.example.com/data.json',
        enabled: true,
      });
    });
  });

  it('triggers a refresh for a feed', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('my-misp')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('Refresh feed my-misp'));

    await waitFor(() => {
      expect(mockedApi.refreshFeed).toHaveBeenCalledWith('f1');
    });
  });

  it('deletes a feed after confirmation', async () => {
    window.confirm = jest.fn(() => true);
    renderPage();
    await waitFor(() => expect(screen.getByText('my-misp')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('Delete feed my-misp'));

    await waitFor(() => {
      expect(mockedApi.deleteFeed).toHaveBeenCalledWith('f1');
    });
  });

  it('does not delete when confirmation is declined', async () => {
    window.confirm = jest.fn(() => false);
    renderPage();
    await waitFor(() => expect(screen.getByText('my-misp')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('Delete feed my-misp'));

    expect(mockedApi.deleteFeed).not.toHaveBeenCalled();
  });

  it('retries fetching after an error', async () => {
    mockedApi.listFeeds.mockRejectedValueOnce(new Error('Failed to fetch'));
    renderPage();

    await waitFor(() => {
      expect(screen.getByText('Error loading data')).toBeInTheDocument();
    });

    mockedApi.listFeeds.mockResolvedValueOnce(mockFeeds);
    fireEvent.click(screen.getByText('Retry'));

    await waitFor(() => {
      expect(screen.getByText('my-misp')).toBeInTheDocument();
    });
  });

  it('requires name and URL before saving', async () => {
    const alertSpy = jest.spyOn(window, 'alert').mockImplementation();
    renderPage();
    await waitFor(() => expect(screen.getByText('my-misp')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('Add new feed source'));
    fireEvent.click(screen.getByText('Save'));

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('Name and URL are required');
    });
    expect(mockedApi.createFeed).not.toHaveBeenCalled();

    alertSpy.mockRestore();
  });

  it('changes the source type and enabled checkbox before saving', async () => {
    const user = userEvent.setup();
    renderPage();
    await waitFor(() => expect(screen.getByText('my-misp')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('Add new feed source'));
    await user.type(screen.getByLabelText('Name'), 'stix-feed');
    await user.type(screen.getByLabelText('URL'), 'https://stix.example.com/feed');
    fireEvent.change(screen.getByLabelText('Source Type'), { target: { value: 'stix' } });
    fireEvent.click(screen.getByLabelText('Enabled'));
    fireEvent.click(screen.getByText('Save'));

    await waitFor(() => {
      expect(mockedApi.createFeed).toHaveBeenCalledWith({
        name: 'stix-feed',
        source_type: 'stix',
        url: 'https://stix.example.com/feed',
        enabled: false,
      });
    });
  });

  it('closes the modal via cancel', async () => {
    renderPage();
    await waitFor(() => expect(screen.getByText('my-misp')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('Add new feed source'));
    await waitFor(() => {
      expect(screen.getByText('Add Feed Source')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Cancel'));

    await waitFor(() => {
      expect(screen.queryByText('Add Feed Source')).not.toBeInTheDocument();
    });
  });

  it('shows an alert when creating a feed fails', async () => {
    const alertSpy = jest.spyOn(window, 'alert').mockImplementation();
    const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation();
    const user = userEvent.setup();
    mockedApi.createFeed.mockRejectedValue(new Error('boom'));
    renderPage();
    await waitFor(() => expect(screen.getByText('my-misp')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('Add new feed source'));
    await user.type(screen.getByLabelText('Name'), 'broken-feed');
    await user.type(screen.getByLabelText('URL'), 'https://broken.example.com/feed');
    fireEvent.click(screen.getByText('Save'));

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('Failed to create feed source');
    });
    expect(consoleErrorSpy).toHaveBeenCalledWith(
      expect.stringContaining('SaveFeed error'),
      expect.any(Object)
    );

    alertSpy.mockRestore();
    consoleErrorSpy.mockRestore();
  });

  it('shows an alert when deleting a feed fails', async () => {
    const alertSpy = jest.spyOn(window, 'alert').mockImplementation();
    const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation();
    window.confirm = jest.fn(() => true);
    mockedApi.deleteFeed.mockRejectedValue(new Error('boom'));
    renderPage();
    await waitFor(() => expect(screen.getByText('my-misp')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('Delete feed my-misp'));

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('Failed to delete feed source');
    });
    expect(consoleErrorSpy).toHaveBeenCalledWith(
      expect.stringContaining('DeleteFeed error'),
      expect.any(Object)
    );

    alertSpy.mockRestore();
    consoleErrorSpy.mockRestore();
  });

  it('shows an alert when refreshing a feed fails', async () => {
    const alertSpy = jest.spyOn(window, 'alert').mockImplementation();
    const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation();
    mockedApi.refreshFeed.mockRejectedValue(new Error('boom'));
    renderPage();
    await waitFor(() => expect(screen.getByText('my-misp')).toBeInTheDocument());

    fireEvent.click(screen.getByLabelText('Refresh feed my-misp'));

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('Failed to refresh feed source');
    });
    expect(consoleErrorSpy).toHaveBeenCalledWith(
      expect.stringContaining('RefreshFeed error'),
      expect.any(Object)
    );

    alertSpy.mockRestore();
    consoleErrorSpy.mockRestore();
  });
});
