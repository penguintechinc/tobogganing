import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { BlockPageBuilder } from './BlockPageBuilder';
import * as saseApi from '../../api/sase';

// Mock the API
jest.mock('../../api/sase');
const mockedSaseApi = saseApi as jest.Mocked<typeof saseApi>;

describe('BlockPageBuilder', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    // Mock API functions
    mockedSaseApi.listBlockPages.mockResolvedValue([]);
    mockedSaseApi.createBlockPage.mockResolvedValue({
      id: 'page-1',
      tenant: 'tenant-1',
      name: 'Test Page',
      markdown: '# Test',
      status: 'draft',
      version: 1,
      created_by: 'user-1',
      updated_by: null,
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    mockedSaseApi.updateBlockPage.mockResolvedValue({
      id: 'page-1',
      tenant: 'tenant-1',
      name: 'Test Page',
      markdown: '# Updated',
      status: 'draft',
      version: 1,
      created_by: 'user-1',
      updated_by: 'user-1',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });
    mockedSaseApi.previewBlockPage.mockResolvedValue({
      html: '<h1>Test</h1>',
      variables: {
        blocked_url: 'example.com',
        category: 'Uncategorized',
      },
    });
  });

  const renderComponent = () => {
    return render(
      <QueryClientProvider client={queryClient}>
        <BlockPageBuilder />
      </QueryClientProvider>
    );
  };

  it('renders the builder with title and initial state', () => {
    renderComponent();
    expect(screen.getByText('Block Page Builder')).toBeInTheDocument();
    expect(screen.getByPlaceholderText('e.g., \'Malware Block Page\'')).toBeInTheDocument();
  });

  it('adds a heading block when clicking add button', async () => {
    renderComponent();

    const h1Button = screen.getByLabelText('Add heading1 block');
    expect(h1Button).toBeInTheDocument();
    fireEvent.click(h1Button);

    await waitFor(() => {
      expect(screen.getByText('Heading 1')).toBeInTheDocument();
    });
  });

  it('serializes blocks to markdown correctly', async () => {
    renderComponent();

    // Add H1 block
    fireEvent.click(screen.getByLabelText('Add heading1 block'));

    await waitFor(() => {
      const h1Blocks = screen.getAllByText('Heading 1');
      expect(h1Blocks.length).toBeGreaterThan(0);
    });

    // Expand the block
    const expandButtons = screen.getAllByLabelText(/Expand block/i);
    expect(expandButtons.length).toBeGreaterThan(0);
    const expandButton = expandButtons[0]!;
    expect(expandButton).toBeInTheDocument();
    fireEvent.click(expandButton);

    // Enter heading text
    const inputs = screen.getAllByPlaceholderText('Enter heading text');
    expect(inputs.length).toBeGreaterThan(0);
    fireEvent.change(inputs[0]!, { target: { value: 'My Block Page' } });

    await waitFor(() => {
      expect(screen.getByText('# My Block Page')).toBeInTheDocument();
    });
  });

  it('serializes text block to markdown', async () => {
    renderComponent();

    fireEvent.click(screen.getByLabelText('Add text block'));

    await waitFor(() => {
      const textLabels = screen.getAllByText('Text/Paragraph');
      expect(textLabels.length).toBeGreaterThan(0);
    });

    const expandButtons = screen.getAllByLabelText(/Expand block/i);
    expect(expandButtons.length).toBeGreaterThan(0);
    fireEvent.click(expandButtons[0]!);

    const textareas = screen.getAllByPlaceholderText(/Enter paragraph text/);
    expect(textareas.length).toBeGreaterThan(0);
    fireEvent.change(textareas[0]!, { target: { value: 'This is a paragraph.' } });

    await waitFor(() => {
      expect(screen.getByText('This is a paragraph.')).toBeInTheDocument();
    });
  });

  it('serializes image block to markdown', async () => {
    renderComponent();

    fireEvent.click(screen.getByLabelText('Add image block'));

    await waitFor(() => {
      const imageLabels = screen.getAllByText('Image');
      expect(imageLabels.length).toBeGreaterThan(0);
    });

    const expandButtons = screen.getAllByLabelText(/Expand block/i);
    expect(expandButtons.length).toBeGreaterThan(0);
    fireEvent.click(expandButtons[0]!);

    const inputs = screen.getAllByPlaceholderText('https://example.com/image.png');
    expect(inputs.length).toBeGreaterThan(0);
    fireEvent.change(inputs[0]!, { target: { value: 'https://example.com/logo.png' } });

    const altInputs = screen.getAllByPlaceholderText('Description of the image');
    expect(altInputs.length).toBeGreaterThan(0);
    fireEvent.change(altInputs[0]!, { target: { value: 'Company Logo' } });

    await waitFor(() => {
      expect(screen.getByText('![Company Logo](https://example.com/logo.png)')).toBeInTheDocument();
    });
  });

  it('serializes link block to markdown', async () => {
    renderComponent();

    fireEvent.click(screen.getByLabelText('Add link block'));

    await waitFor(() => {
      const linkLabels = screen.getAllByText('Link/Button');
      expect(linkLabels.length).toBeGreaterThan(0);
    });

    const expandButtons = screen.getAllByLabelText(/Expand block/i);
    expect(expandButtons.length).toBeGreaterThan(0);
    fireEvent.click(expandButtons[0]!);

    const inputs = screen.getAllByPlaceholderText('Click here');
    expect(inputs.length).toBeGreaterThan(0);
    fireEvent.change(inputs[0]!, { target: { value: 'Appeal Now' } });

    const urlInputs = screen.getAllByPlaceholderText('https://example.com');
    expect(urlInputs.length).toBeGreaterThan(0);
    fireEvent.change(urlInputs[0]!, { target: { value: 'https://appeal.example.com' } });

    await waitFor(() => {
      expect(screen.getByText('[Appeal Now](https://appeal.example.com)')).toBeInTheDocument();
    });
  });

  it('serializes list block to markdown', async () => {
    renderComponent();

    fireEvent.click(screen.getByLabelText('Add list block'));

    await waitFor(() => {
      const listLabels = screen.getAllByText('List');
      expect(listLabels.length).toBeGreaterThan(0);
    });

    const expandButtons = screen.getAllByLabelText(/Expand block/i);
    expect(expandButtons.length).toBeGreaterThan(0);
    fireEvent.click(expandButtons[0]!);

    const textareas = screen.getAllByPlaceholderText(/Item 1/);
    expect(textareas.length).toBeGreaterThan(0);
    fireEvent.change(textareas[0]!, { target: { value: 'Item 1\nItem 2\nItem 3' } });

    await waitFor(() => {
      expect(screen.getByText('- Item 1')).toBeInTheDocument();
      expect(screen.getByText('- Item 2')).toBeInTheDocument();
      expect(screen.getByText('- Item 3')).toBeInTheDocument();
    });
  });

  it('serializes divider block to markdown', async () => {
    renderComponent();

    fireEvent.click(screen.getByLabelText('Add divider block'));

    await waitFor(() => {
      const dividerLabels = screen.getAllByText('Divider');
      expect(dividerLabels.length).toBeGreaterThan(0);
    });

    await waitFor(() => {
      expect(screen.getByText('---')).toBeInTheDocument();
    });
  });

  it('removes a block when trash button clicked', async () => {
    renderComponent();

    fireEvent.click(screen.getByLabelText('Add heading1 block'));

    await waitFor(() => {
      const h1Blocks = screen.getAllByText('Heading 1');
      expect(h1Blocks.length).toBeGreaterThan(0);
    });

    // Get the remove button for the block
    const removeButtons = screen.getAllByLabelText(/Remove.*block/i);
    expect(removeButtons.length).toBeGreaterThan(0);
    const removeButton = removeButtons[0]!;
    expect(removeButton).toBeInTheDocument();
    fireEvent.click(removeButton);

    await waitFor(() => {
      const h1Blocks = screen.queryAllByText('Heading 1');
      expect(h1Blocks.length).toBe(0);
    });
  });

  it('saves page with markdown content', async () => {
    renderComponent();

    // Enter page name
    const pageName = screen.getByPlaceholderText('e.g., \'Malware Block Page\'');
    fireEvent.change(pageName, { target: { value: 'Malware Block' } });

    // Add a block
    fireEvent.click(screen.getByLabelText('Add heading1 block'));

    await waitFor(() => {
      const h1Blocks = screen.getAllByText('Heading 1');
      expect(h1Blocks.length).toBeGreaterThan(0);
    });

    // Save
    const saveButton = screen.getByText('Save');
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(mockedSaseApi.createBlockPage).toHaveBeenCalled();
    });
  });

  it('shows page name required error', async () => {
    renderComponent();

    // Add a block
    fireEvent.click(screen.getByLabelText('Add heading1 block'));

    await waitFor(() => {
      const h1Blocks = screen.getAllByText('Heading 1');
      expect(h1Blocks.length).toBeGreaterThan(0);
    });

    // Try to save without a page name
    const saveButton = screen.getByText('Save');
    fireEvent.click(saveButton);

    await waitFor(() => {
      expect(screen.getByText('Please enter a page name')).toBeInTheDocument();
    });
  });

  it('renders multiple blocks in order', async () => {
    renderComponent();

    // Add H1
    fireEvent.click(screen.getByLabelText('Add heading1 block'));
    // Add text
    fireEvent.click(screen.getByLabelText('Add text block'));
    // Add divider
    fireEvent.click(screen.getByLabelText('Add divider block'));

    await waitFor(() => {
      const headingLabels = screen.getAllByText('Heading 1');
      const textLabels = screen.getAllByText('Text/Paragraph');
      const dividerLabels = screen.getAllByText('Divider');

      expect(headingLabels.length).toBeGreaterThan(0);
      expect(textLabels.length).toBeGreaterThan(0);
      expect(dividerLabels.length).toBeGreaterThan(0);
    });

    // Verify blocks are displayed
    const blocks = screen.getAllByText(/Heading 1|Text\/Paragraph|Divider/);
    expect(blocks.length).toBeGreaterThan(0);
  });

  it('console logs block operations', async () => {
    const consoleSpy = jest.spyOn(console, 'log').mockImplementation();

    renderComponent();
    fireEvent.click(screen.getByLabelText('Add heading1 block'));

    await waitFor(() => {
      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining('[BlockPageBuilder]'),
        expect.any(Object)
      );
    });

    consoleSpy.mockRestore();
  });
});
