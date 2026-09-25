import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { IocCheckPage } from './IocCheckPage';
import * as threatintelApi from '../../api/threatintel';

// Partial mock: preserve real constant exports (IOC_TYPES) via
// requireActual — full automock reduces `as const` array exports to `[]`,
// which breaks the page's <option> rendering logic.
jest.mock('../../api/threatintel', () => ({
  ...jest.requireActual('../../api/threatintel'),
  checkIoc: jest.fn(),
}));
const mockedApi = threatintelApi as jest.Mocked<typeof threatintelApi>;

describe('IocCheckPage', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    jest.clearAllMocks();
  });

  const renderPage = () =>
    render(
      <QueryClientProvider client={queryClient}>
        <IocCheckPage />
      </QueryClientProvider>
    );

  it('renders the page title', () => {
    renderPage();
    expect(screen.getByText('IOC Check')).toBeInTheDocument();
  });

  it('does not submit when the value is empty', () => {
    renderPage();
    expect(screen.getByLabelText('Check indicator against blocklist')).toBeDisabled();
  });

  it('shows a blocked verdict when the indicator is found', async () => {
    mockedApi.checkIoc.mockResolvedValue({
      ioc_type: 'domain',
      value: 'malicious.example.com',
      severity: 'high',
      source: 'misp',
      stix_id: 'indicator--abc',
      first_seen: 1700000000,
      expiry: null,
    });
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText('Indicator value'), 'malicious.example.com');
    fireEvent.click(screen.getByLabelText('Check indicator against blocklist'));

    await waitFor(() => {
      expect(screen.getByTestId('ioc-verdict-blocked')).toBeInTheDocument();
      expect(screen.getByText('malicious.example.com')).toBeInTheDocument();
    });
    expect(mockedApi.checkIoc).toHaveBeenCalledWith('domain', 'malicious.example.com');
  });

  it('shows a clean verdict when the indicator is not found', async () => {
    mockedApi.checkIoc.mockResolvedValue(null);
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText('Indicator value'), 'clean.example.com');
    fireEvent.click(screen.getByLabelText('Check indicator against blocklist'));

    await waitFor(() => {
      expect(screen.getByTestId('ioc-verdict-clean')).toBeInTheDocument();
    });
  });

  it('shows an error message when the lookup fails', async () => {
    mockedApi.checkIoc.mockRejectedValue(new Error('Network error'));
    const user = userEvent.setup();
    renderPage();

    await user.type(screen.getByLabelText('Indicator value'), 'clean.example.com');
    fireEvent.click(screen.getByLabelText('Check indicator against blocklist'));

    await waitFor(() => {
      expect(screen.getByText('Lookup failed')).toBeInTheDocument();
      expect(screen.getByText('Network error')).toBeInTheDocument();
    });
  });
});
