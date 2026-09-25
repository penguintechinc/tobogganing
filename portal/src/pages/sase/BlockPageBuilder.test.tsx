import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { DragEndEvent } from '@dnd-kit/core';
import { BlockPageBuilder } from './BlockPageBuilder';
import * as saseApi from '../../api/sase';
import type { BlockPage } from '../../api/sase';

// Mock react-markdown to avoid ESM transform issues
jest.mock('react-markdown', () => ({
  __esModule: true,
  default: ({ children }: { children: React.ReactNode }) => (
    <div data-testid="markdown-preview">{children}</div>
  ),
}));

// Mock the API
jest.mock('../../api/sase');
const mockedSaseApi = saseApi as jest.Mocked<typeof saseApi>;

// Capture the onDragEnd handler passed to DndContext so drag-reorder logic
// can be exercised directly without simulating full pointer drag sequences.
let mockCapturedOnDragEnd: ((event: DragEndEvent) => void) | undefined;
jest.mock('@dnd-kit/core', () => {
  const actual = jest.requireActual('@dnd-kit/core');
  return {
    ...actual,
    DndContext: (props: Record<string, unknown>) => {
      mockCapturedOnDragEnd = props.onDragEnd as (event: DragEndEvent) => void;
      const ActualDndContext = actual.DndContext;
      return <ActualDndContext {...props} />;
    },
  };
});

describe('BlockPageBuilder', () => {
  let queryClient: QueryClient;

  beforeEach(() => {
    jest.clearAllMocks();
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
    expect(screen.getByPlaceholderText("e.g., 'Malware Block Page'")).toBeInTheDocument();
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

    // Verify markdown output contains the text (in the generated markdown <pre> block)
    await waitFor(() => {
      const markdownOutput = screen.getByText(/This is a paragraph\./, { selector: 'pre' });
      expect(markdownOutput).toBeInTheDocument();
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

    // Verify markdown output contains the list items (in the generated markdown <pre> block)
    await waitFor(() => {
      const markdownOutput = screen.getByText(/- Item 1[\s\S]*- Item 2[\s\S]*- Item 3/, {
        selector: 'pre',
      });
      expect(markdownOutput).toBeInTheDocument();
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
    const pageName = screen.getByPlaceholderText("e.g., 'Malware Block Page'");
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
    const alertSpy = jest.spyOn(window, 'alert').mockImplementation();

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
      expect(alertSpy).toHaveBeenCalledWith('Please enter a page name');
    });

    alertSpy.mockRestore();
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

  it.each([
    ['heading2', '##'],
    ['heading3', '###'],
    ['heading4', '####'],
  ])('serializes %s block to markdown', async (type, prefix) => {
    renderComponent();

    fireEvent.click(screen.getByLabelText(`Add ${type} block`));

    const expandButtons = await waitFor(() => {
      const buttons = screen.getAllByLabelText(/Expand block/i);
      expect(buttons.length).toBeGreaterThan(0);
      return buttons;
    });
    fireEvent.click(expandButtons[0]!);

    const inputs = screen.getAllByPlaceholderText('Enter heading text');
    fireEvent.change(inputs[0]!, { target: { value: 'Test' } });

    await waitFor(() => {
      expect(screen.getByText(`${prefix} Test`)).toBeInTheDocument();
    });
  });

  it('toggles the preview panel visibility', async () => {
    renderComponent();

    const toggleButton = screen.getByLabelText('Show preview');
    expect(screen.getByText('Show Preview')).toBeInTheDocument();

    fireEvent.click(toggleButton);

    await waitFor(() => {
      expect(screen.getByLabelText('Hide preview')).toBeInTheDocument();
      expect(screen.getByText('Hide Preview')).toBeInTheDocument();
    });
  });

  it('reorders blocks when a drag-end event fires with a different position', async () => {
    let now = 1000;
    jest.spyOn(Date, 'now').mockImplementation(() => now++);
    const consoleSpy = jest.spyOn(console, 'log').mockImplementation();

    renderComponent();

    fireEvent.click(screen.getByLabelText('Add heading1 block'));
    fireEvent.click(screen.getByLabelText('Add text block'));

    await waitFor(() => {
      expect(screen.getAllByText('Heading 1').length).toBeGreaterThan(0);
      expect(screen.getAllByText('Text/Paragraph').length).toBeGreaterThan(0);
    });

    expect(mockCapturedOnDragEnd).toBeDefined();

    act(() => {
      mockCapturedOnDragEnd!({
        active: { id: 'block-1000' },
        over: { id: 'block-1001' },
      } as DragEndEvent);
    });

    await waitFor(() => {
      expect(consoleSpy).toHaveBeenCalledWith(
        expect.stringContaining('Reorder'),
        expect.objectContaining({ oldIndex: 0, newIndex: 1 })
      );
    });

    consoleSpy.mockRestore();
  });

  it('does not reorder when drag ends over the same block', async () => {
    let now = 2000;
    jest.spyOn(Date, 'now').mockImplementation(() => now++);
    const consoleSpy = jest.spyOn(console, 'log').mockImplementation();

    renderComponent();
    fireEvent.click(screen.getByLabelText('Add heading1 block'));

    await waitFor(() => {
      expect(screen.getAllByText('Heading 1').length).toBeGreaterThan(0);
    });

    expect(mockCapturedOnDragEnd).toBeDefined();
    consoleSpy.mockClear();

    act(() => {
      mockCapturedOnDragEnd!({
        active: { id: 'block-2000' },
        over: { id: 'block-2000' },
      } as DragEndEvent);
    });

    expect(consoleSpy).not.toHaveBeenCalledWith(
      expect.stringContaining('Reorder'),
      expect.anything()
    );

    consoleSpy.mockRestore();
  });

  it('does not reorder when drag ends without a drop target', async () => {
    const consoleSpy = jest.spyOn(console, 'log').mockImplementation();

    renderComponent();
    fireEvent.click(screen.getByLabelText('Add heading1 block'));

    await waitFor(() => {
      expect(screen.getAllByText('Heading 1').length).toBeGreaterThan(0);
    });

    expect(mockCapturedOnDragEnd).toBeDefined();
    consoleSpy.mockClear();

    act(() => {
      mockCapturedOnDragEnd!({
        active: { id: 'block-1' },
        over: null,
      } as unknown as DragEndEvent);
    });

    expect(consoleSpy).not.toHaveBeenCalledWith(
      expect.stringContaining('Reorder'),
      expect.anything()
    );

    consoleSpy.mockRestore();
  });

  const existingPage: BlockPage = {
    id: 'page-2',
    tenant: 'tenant-1',
    name: 'Existing Page',
    markdown: '# Hi',
    status: 'draft',
    version: 1,
    created_by: 'user-1',
    updated_by: null,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  };

  it('loads an existing page from the dropdown', async () => {
    mockedSaseApi.listBlockPages.mockResolvedValue([existingPage]);

    renderComponent();

    const select = await screen.findByRole('combobox');
    fireEvent.change(select, { target: { value: 'page-2' } });

    await waitFor(() => {
      expect(screen.getByPlaceholderText("e.g., 'Malware Block Page'")).toHaveValue(
        'Existing Page'
      );
      expect(screen.getByText('Publish')).toBeInTheDocument();
    });
  });

  it('does not error selecting the blank dropdown option', async () => {
    mockedSaseApi.listBlockPages.mockResolvedValue([existingPage]);

    renderComponent();

    const select = await screen.findByRole('combobox');
    fireEvent.change(select, { target: { value: '' } });

    expect(screen.getByPlaceholderText("e.g., 'Malware Block Page'")).toHaveValue('');
  });

  it('updates an existing page on save instead of creating a new one', async () => {
    mockedSaseApi.listBlockPages.mockResolvedValue([existingPage]);

    renderComponent();

    const select = await screen.findByRole('combobox');
    fireEvent.change(select, { target: { value: 'page-2' } });

    await waitFor(() => {
      expect(screen.getByText('Publish')).toBeInTheDocument();
    });

    fireEvent.click(screen.getByText('Save'));

    await waitFor(() => {
      expect(mockedSaseApi.updateBlockPage).toHaveBeenCalledWith('page-2', expect.any(String));
    });
    expect(mockedSaseApi.createBlockPage).not.toHaveBeenCalled();
  });

  it('shows an alert when saving fails', async () => {
    const alertSpy = jest.spyOn(window, 'alert').mockImplementation();
    const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation();
    mockedSaseApi.createBlockPage.mockRejectedValue(new Error('network error'));

    renderComponent();

    fireEvent.change(screen.getByPlaceholderText("e.g., 'Malware Block Page'"), {
      target: { value: 'Broken Page' },
    });
    fireEvent.click(screen.getByText('Save'));

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('Failed to save page');
    });
    expect(consoleErrorSpy).toHaveBeenCalledWith(
      expect.stringContaining('SavePage error'),
      expect.any(Object)
    );

    alertSpy.mockRestore();
    consoleErrorSpy.mockRestore();
  });

  it('publishes an existing page successfully', async () => {
    const alertSpy = jest.spyOn(window, 'alert').mockImplementation();
    mockedSaseApi.listBlockPages.mockResolvedValue([existingPage]);
    mockedSaseApi.publishBlockPage.mockResolvedValue({ ...existingPage, status: 'live' });

    renderComponent();

    const select = await screen.findByRole('combobox');
    fireEvent.change(select, { target: { value: 'page-2' } });

    await waitFor(() => {
      expect(screen.getByText('Publish')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('Publish'));

    await waitFor(() => {
      expect(mockedSaseApi.publishBlockPage).toHaveBeenCalledWith('page-2');
      expect(alertSpy).toHaveBeenCalledWith('Page published!');
    });

    alertSpy.mockRestore();
  });

  it('shows an alert when publishing fails', async () => {
    const alertSpy = jest.spyOn(window, 'alert').mockImplementation();
    const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation();
    mockedSaseApi.listBlockPages.mockResolvedValue([existingPage]);
    mockedSaseApi.publishBlockPage.mockRejectedValue(new Error('boom'));

    renderComponent();

    const select = await screen.findByRole('combobox');
    fireEvent.change(select, { target: { value: 'page-2' } });

    await waitFor(() => {
      expect(screen.getByText('Publish')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('Publish'));

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('Failed to publish page');
    });
    expect(consoleErrorSpy).toHaveBeenCalledWith(
      expect.stringContaining('PublishPage error'),
      expect.any(Object)
    );

    alertSpy.mockRestore();
    consoleErrorSpy.mockRestore();
  });

  it('generates a preview for an existing page successfully', async () => {
    mockedSaseApi.listBlockPages.mockResolvedValue([existingPage]);

    renderComponent();

    const select = await screen.findByRole('combobox');
    fireEvent.change(select, { target: { value: 'page-2' } });

    await waitFor(() => {
      expect(screen.getByText('Preview')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('Preview'));

    await waitFor(() => {
      expect(mockedSaseApi.previewBlockPage).toHaveBeenCalledWith('page-2');
      expect(screen.getByTestId('markdown-preview')).toBeInTheDocument();
    });
  });

  it('shows an alert when preview generation fails', async () => {
    const alertSpy = jest.spyOn(window, 'alert').mockImplementation();
    const consoleErrorSpy = jest.spyOn(console, 'error').mockImplementation();
    mockedSaseApi.listBlockPages.mockResolvedValue([existingPage]);
    mockedSaseApi.previewBlockPage.mockRejectedValue(new Error('boom'));

    renderComponent();

    const select = await screen.findByRole('combobox');
    fireEvent.change(select, { target: { value: 'page-2' } });

    await waitFor(() => {
      expect(screen.getByText('Preview')).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText('Preview'));

    await waitFor(() => {
      expect(alertSpy).toHaveBeenCalledWith('Failed to generate preview');
    });
    expect(consoleErrorSpy).toHaveBeenCalledWith(
      expect.stringContaining('Preview error'),
      expect.any(Object)
    );

    alertSpy.mockRestore();
    consoleErrorSpy.mockRestore();
  });
});
