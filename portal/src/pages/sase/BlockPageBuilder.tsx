import React, { useState, useCallback, useMemo } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { ChevronDown, ChevronUp, Trash2, Plus, Eye } from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import {
  DndContext,
  closestCenter,
  KeyboardSensor,
  PointerSensor,
  useSensor,
  useSensors,
  DragEndEvent,
} from '@dnd-kit/core';
import {
  arrayMove,
  SortableContext,
  sortableKeyboardCoordinates,
  verticalListSortingStrategy,
} from '@dnd-kit/sortable';
import { useSortable } from '@dnd-kit/sortable';
import { CSS } from '@dnd-kit/utilities';
import {
  listBlockPages,
  createBlockPage,
  updateBlockPage,
  publishBlockPage,
  previewBlockPage,
  type BlockPage,
  type BlockPagePreview,
} from '../../api/sase';

/** A markdown element block */
export interface MarkdownBlock {
  id: string;
  type: 'heading1' | 'heading2' | 'heading3' | 'heading4' | 'text' | 'image' | 'link' | 'list' | 'divider';
  content: Record<string, string>;
}

/** Draggable block editor */
function SortableBlockEditor({
  block,
  onUpdate,
  onRemove,
}: {
  block: MarkdownBlock;
  onUpdate: (block: MarkdownBlock) => void;
  onRemove: () => void;
}) {
  const { attributes, listeners, setNodeRef, transform, transition, isDragging } = useSortable({
    id: block.id,
  });

  const style = {
    transform: CSS.Transform.toString(transform),
    transition,
    opacity: isDragging ? 0.5 : 1,
  };

  const [isExpanded, setIsExpanded] = useState(false);

  const updateContent = (key: string, value: string) => {
    onUpdate({
      ...block,
      content: { ...block.content, [key]: value },
    });
  };

  const blockTypeLabel = {
    heading1: 'Heading 1',
    heading2: 'Heading 2',
    heading3: 'Heading 3',
    heading4: 'Heading 4',
    text: 'Text/Paragraph',
    image: 'Image',
    link: 'Link/Button',
    list: 'List',
    divider: 'Divider',
  }[block.type];

  return (
    <div
      ref={setNodeRef}
      style={style}
      className="bg-slate-700 rounded-lg p-4 border border-slate-600 space-y-3"
    >
      <div className="flex items-center justify-between gap-2">
        <button
          {...attributes}
          {...listeners}
          className="flex items-center gap-2 cursor-grab active:cursor-grabbing text-slate-300"
          aria-label={`Drag handle for ${blockTypeLabel} block`}
        >
          <div className="text-amber-400">☰</div>
          <span className="text-sm font-semibold text-amber-400">{blockTypeLabel}</span>
        </button>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setIsExpanded(!isExpanded)}
            className="text-slate-300 hover:text-amber-400 transition-colors"
            aria-label={isExpanded ? 'Collapse block' : 'Expand block'}
          >
            {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
          </button>
          <button
            onClick={onRemove}
            className="text-red-400 hover:text-red-300 transition-colors"
            aria-label={`Remove ${blockTypeLabel} block`}
          >
            <Trash2 size={16} />
          </button>
        </div>
      </div>

      {isExpanded && (
        <div className="space-y-3 pl-4">
          {block.type.startsWith('heading') && (
            <div>
              <label className="block text-sm text-slate-300 mb-1">Heading Text</label>
              <input
                type="text"
                value={block.content.text || ''}
                onChange={(e) => updateContent('text', e.target.value)}
                placeholder="Enter heading text"
                className="w-full bg-slate-600 text-white px-2 py-1 rounded border border-slate-500 focus:border-amber-400 focus:outline-none"
              />
            </div>
          )}

          {block.type === 'text' && (
            <div>
              <label className="block text-sm text-slate-300 mb-1">Paragraph Text</label>
              <textarea
                value={block.content.text || ''}
                onChange={(e) => updateContent('text', e.target.value)}
                placeholder="Enter paragraph text. Supports {{template_variables}}"
                rows={3}
                className="w-full bg-slate-600 text-white px-2 py-1 rounded border border-slate-500 focus:border-amber-400 focus:outline-none"
              />
            </div>
          )}

          {block.type === 'image' && (
            <>
              <div>
                <label className="block text-sm text-slate-300 mb-1">Image URL</label>
                <input
                  type="text"
                  value={block.content.url || ''}
                  onChange={(e) => updateContent('url', e.target.value)}
                  placeholder="https://example.com/image.png"
                  className="w-full bg-slate-600 text-white px-2 py-1 rounded border border-slate-500 focus:border-amber-400 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-sm text-slate-300 mb-1">Alt Text</label>
                <input
                  type="text"
                  value={block.content.alt || ''}
                  onChange={(e) => updateContent('alt', e.target.value)}
                  placeholder="Description of the image"
                  className="w-full bg-slate-600 text-white px-2 py-1 rounded border border-slate-500 focus:border-amber-400 focus:outline-none"
                />
              </div>
            </>
          )}

          {block.type === 'link' && (
            <>
              <div>
                <label className="block text-sm text-slate-300 mb-1">Link Text</label>
                <input
                  type="text"
                  value={block.content.text || ''}
                  onChange={(e) => updateContent('text', e.target.value)}
                  placeholder="Click here"
                  className="w-full bg-slate-600 text-white px-2 py-1 rounded border border-slate-500 focus:border-amber-400 focus:outline-none"
                />
              </div>
              <div>
                <label className="block text-sm text-slate-300 mb-1">URL</label>
                <input
                  type="text"
                  value={block.content.href || ''}
                  onChange={(e) => updateContent('href', e.target.value)}
                  placeholder="https://example.com"
                  className="w-full bg-slate-600 text-white px-2 py-1 rounded border border-slate-500 focus:border-amber-400 focus:outline-none"
                />
              </div>
            </>
          )}

          {block.type === 'list' && (
            <div>
              <label className="block text-sm text-slate-300 mb-1">List Items (one per line)</label>
              <textarea
                value={block.content.items || ''}
                onChange={(e) => updateContent('items', e.target.value)}
                placeholder="Item 1&#10;Item 2&#10;Item 3"
                rows={4}
                className="w-full bg-slate-600 text-white px-2 py-1 rounded border border-slate-500 focus:border-amber-400 focus:outline-none font-mono text-xs"
              />
            </div>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * BlockPageBuilder — drag-drop markdown element builder
 *
 * Allows users to build block pages by dragging and dropping markdown elements,
 * editing their content, and previewing the rendered markdown. Save/publish functionality.
 */
export function BlockPageBuilder() {
  const [blocks, setBlocks] = useState<MarkdownBlock[]>([]);
  const [pageName, setPageName] = useState('');
  const [pageId, setPageId] = useState<string | null>(null);
  const [showPreview, setShowPreview] = useState(false);
  const [previewData, setPreviewData] = useState<BlockPagePreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  const queryClient = useQueryClient();

  const sensors = useSensors(
    useSensor(PointerSensor),
    useSensor(KeyboardSensor, { coordinateGetter: sortableKeyboardCoordinates })
  );

  console.log('[BlockPageBuilder] Render { pageName, blockCount }', { pageName, blockCount: blocks.length });

  // Load existing pages
  const { data: pages = [] } = useQuery({
    queryKey: ['blockpages', 'pages'],
    queryFn: listBlockPages,
  });

  // Serialize blocks to markdown
  const serializeMarkdown = useCallback((): string => {
    return blocks
      .map((block) => {
        switch (block.type) {
          case 'heading1':
            return `# ${block.content.text || ''}`;
          case 'heading2':
            return `## ${block.content.text || ''}`;
          case 'heading3':
            return `### ${block.content.text || ''}`;
          case 'heading4':
            return `#### ${block.content.text || ''}`;
          case 'text':
            return block.content.text || '';
          case 'image':
            return `![${block.content.alt || 'image'}](${block.content.url || ''})`;
          case 'link':
            return `[${block.content.text || 'link'}](${block.content.href || ''})`;
          case 'list':
            return (block.content.items || '')
              .split('\n')
              .filter((item) => item.trim())
              .map((item) => `- ${item}`)
              .join('\n');
          case 'divider':
            return '---';
          default:
            return '';
        }
      })
      .join('\n\n');
  }, [blocks]);

  // Handle drag end
  const handleDragEnd = (event: DragEndEvent) => {
    const { active, over } = event;

    if (over && active.id !== over.id) {
      const oldIndex = blocks.findIndex((b) => b.id === active.id);
      const newIndex = blocks.findIndex((b) => b.id === over.id);
      setBlocks(arrayMove(blocks, oldIndex, newIndex));
      console.log('[BlockPageBuilder] Reorder { oldIndex, newIndex }', { oldIndex, newIndex });
    }
  };

  // Add a new block
  const addBlock = (type: MarkdownBlock['type']) => {
    const newBlock: MarkdownBlock = {
      id: `block-${Date.now()}`,
      type,
      content: {},
    };
    setBlocks([...blocks, newBlock]);
    console.log('[BlockPageBuilder] AddBlock { type }', { type });
  };

  // Update a block
  const updateBlock = (updatedBlock: MarkdownBlock) => {
    setBlocks(blocks.map((b) => (b.id === updatedBlock.id ? updatedBlock : b)));
  };

  // Remove a block
  const removeBlock = (id: string) => {
    setBlocks(blocks.filter((b) => b.id !== id));
    console.log('[BlockPageBuilder] RemoveBlock { id }', { id });
  };

  // Load a page
  const loadPage = (page: BlockPage) => {
    console.log('[BlockPageBuilder] LoadPage { pageId }', { pageId: page.id });
    setPageName(page.name);
    setPageId(page.id);
    // Parse markdown back to blocks (simplified: split by paragraphs)
    // In a real app, you'd have a markdown parser
    setBlocks([]);
  };

  // Save page
  const handleSave = async () => {
    setIsSaving(true);
    try {
      const markdown = serializeMarkdown();
      if (!pageName.trim()) {
        alert('Please enter a page name');
        setIsSaving(false);
        return;
      }

      if (pageId) {
        await updateBlockPage(pageId, markdown);
        console.log('[BlockPageBuilder] UpdatePage success { pageId }', { pageId });
      } else {
        const newPage = await createBlockPage(pageName, markdown);
        setPageId(newPage.id);
        console.log('[BlockPageBuilder] CreatePage success { pageId }', { pageId: newPage.id });
      }

      queryClient.invalidateQueries({ queryKey: ['blockpages', 'pages'] });
    } catch (error) {
      console.error('[BlockPageBuilder] SavePage error', { error: String(error) });
      alert('Failed to save page');
    } finally {
      setIsSaving(false);
    }
  };

  // Publish page
  const handlePublish = async () => {
    if (!pageId) {
      alert('Please save the page first');
      return;
    }

    try {
      await publishBlockPage(pageId);
      console.log('[BlockPageBuilder] PublishPage success { pageId }', { pageId });
      queryClient.invalidateQueries({ queryKey: ['blockpages', 'pages'] });
      alert('Page published!');
    } catch (error) {
      console.error('[BlockPageBuilder] PublishPage error', { error: String(error) });
      alert('Failed to publish page');
    }
  };

  // Preview
  const handlePreview = async () => {
    if (!pageId) {
      alert('Please save the page first');
      return;
    }

    setPreviewLoading(true);
    try {
      const preview = await previewBlockPage(pageId);
      setPreviewData(preview);
      setShowPreview(true);
      console.log('[BlockPageBuilder] Preview success { pageId }', { pageId });
    } catch (error) {
      console.error('[BlockPageBuilder] Preview error', { error: String(error) });
      alert('Failed to generate preview');
    } finally {
      setPreviewLoading(false);
    }
  };

  const markdown = useMemo(() => serializeMarkdown(), [serializeMarkdown]);
  const blockIds = useMemo(() => blocks.map((b) => b.id), [blocks]);

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold text-amber-400">Block Page Builder</h1>
        <button
          onClick={() => setShowPreview(!showPreview)}
          className="flex items-center gap-2 px-3 py-2 bg-sky-600 hover:bg-sky-700 text-white rounded transition-colors"
          aria-label={showPreview ? 'Hide preview' : 'Show preview'}
        >
          <Eye size={16} />
          {showPreview ? 'Hide Preview' : 'Show Preview'}
        </button>
      </div>

      {/* Page Name & Actions */}
      <div className="bg-slate-800 rounded-lg p-4 space-y-3">
        <div>
          <label className="block text-sm text-slate-300 mb-1">Page Name</label>
          <input
            type="text"
            value={pageName}
            onChange={(e) => setPageName(e.target.value)}
            placeholder="e.g., 'Malware Block Page'"
            className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none"
          />
        </div>

        <div className="flex gap-2 flex-wrap">
          <button
            onClick={handleSave}
            disabled={isSaving}
            className="px-4 py-2 bg-green-600 hover:bg-green-700 text-white rounded disabled:opacity-50 transition-colors"
          >
            {isSaving ? 'Saving...' : 'Save'}
          </button>
          {pageId && (
            <>
              <button
                onClick={handlePublish}
                className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded transition-colors"
              >
                Publish
              </button>
              <button
                onClick={handlePreview}
                disabled={previewLoading}
                className="px-4 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded disabled:opacity-50 transition-colors"
              >
                {previewLoading ? 'Loading...' : 'Preview'}
              </button>
            </>
          )}
        </div>

        {/* Load Existing Page */}
        {pages.length > 0 && (
          <div>
            <label className="block text-sm text-slate-300 mb-2">Load Existing Page</label>
            <select
              onChange={(e) => {
                const page = pages.find((p) => p.id === e.target.value);
                if (page) loadPage(page);
              }}
              className="w-full bg-slate-700 text-white px-3 py-2 rounded border border-slate-600 focus:border-amber-400 focus:outline-none"
            >
              <option value="">-- Select a page --</option>
              {pages.map((page) => (
                <option key={page.id} value={page.id}>
                  {page.name} ({page.status})
                </option>
              ))}
            </select>
          </div>
        )}
      </div>

      <div className={showPreview ? 'grid grid-cols-2 gap-4' : ''}>
        {/* Block Editor */}
        <div className="space-y-3">
          <h2 className="text-lg font-semibold text-amber-400">Blocks</h2>

          {/* Add Block Palette */}
          <div className="bg-slate-800 rounded-lg p-4">
            <p className="text-sm text-slate-300 mb-3">Add blocks:</p>
            <div className="grid grid-cols-2 gap-2">
              {(['heading1', 'heading2', 'heading3', 'heading4', 'text', 'image', 'link', 'list', 'divider'] as const).map(
                (type) => (
                  <button
                    key={type}
                    onClick={() => addBlock(type)}
                    className="flex items-center gap-2 px-2 py-2 bg-slate-700 hover:bg-sky-600 text-white rounded text-xs transition-colors"
                    aria-label={`Add ${type} block`}
                  >
                    <Plus size={14} />
                    {type === 'heading1'
                      ? 'H1'
                      : type === 'heading2'
                        ? 'H2'
                        : type === 'heading3'
                          ? 'H3'
                          : type === 'heading4'
                            ? 'H4'
                            : type === 'text'
                              ? 'Text'
                              : type}
                  </button>
                )
              )}
            </div>
          </div>

          {/* Draggable Blocks */}
          {blocks.length > 0 ? (
            <DndContext sensors={sensors} collisionDetection={closestCenter} onDragEnd={handleDragEnd}>
              <SortableContext items={blockIds} strategy={verticalListSortingStrategy}>
                <div className="space-y-3">
                  {blocks.map((block) => (
                    <SortableBlockEditor
                      key={block.id}
                      block={block}
                      onUpdate={updateBlock}
                      onRemove={() => removeBlock(block.id)}
                    />
                  ))}
                </div>
              </SortableContext>
            </DndContext>
          ) : (
            <div className="bg-slate-700 rounded-lg p-4 text-center text-slate-400">
              Add blocks to get started →
            </div>
          )}

          {/* Markdown Output */}
          <div className="bg-slate-800 rounded-lg p-4">
            <p className="text-sm text-slate-300 mb-2">Generated Markdown:</p>
            <pre className="bg-slate-900 p-3 rounded text-xs text-amber-100 overflow-x-auto max-h-40 font-mono">
              {markdown || '(empty)'}
            </pre>
          </div>
        </div>

        {/* Preview */}
        {showPreview && previewData && (
          <div className="space-y-3">
            <h2 className="text-lg font-semibold text-amber-400">Preview</h2>
            <div className="bg-white dark:bg-slate-900 rounded-lg p-4 prose prose-sm dark:prose-invert max-w-none overflow-y-auto max-h-96 border border-slate-600">
              <ReactMarkdown>{markdown}</ReactMarkdown>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
