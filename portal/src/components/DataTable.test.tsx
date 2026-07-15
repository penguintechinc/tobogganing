import { render, screen, fireEvent } from '@testing-library/react';
import { DataTable, ColumnConfig } from './DataTable';

interface TestRow {
  id: string;
  name: string;
  value: number;
}

describe('DataTable', () => {
  const testData: TestRow[] = [
    { id: '1', name: 'Alice', value: 100 },
    { id: '2', name: 'Bob', value: 50 },
    { id: '3', name: 'Charlie', value: 75 },
  ];

  const columns: ColumnConfig<TestRow>[] = [
    { key: 'name', label: 'Name', sortable: true },
    { key: 'value', label: 'Value', sortable: true },
  ];

  it('renders datatable with data', () => {
    render(
      <DataTable columns={columns} data={testData} pageSize={25} />
    );

    const table = screen.getByTestId('datatable');
    expect(table).toBeInTheDocument();

    expect(screen.getByText('Alice')).toBeInTheDocument();
    expect(screen.getByText('Bob')).toBeInTheDocument();
  });

  it('shows loading skeleton when loading', () => {
    render(<DataTable columns={columns} data={[]} isLoading={true} />);

    const table = screen.getByTestId('datatable');
    const pulseDiv = table.querySelector('.animate-pulse');
    expect(pulseDiv).toBeInTheDocument();
  });

  it('shows error state with retry button', () => {
    const error = new Error('Test error');
    const onRetry = jest.fn();

    render(
      <DataTable
        columns={columns}
        data={[]}
        error={error}
        onRetry={onRetry}
      />
    );

    expect(screen.getByText('Error loading data')).toBeInTheDocument();
    expect(screen.getByText('Test error')).toBeInTheDocument();

    const retryBtn = screen.getByText('Retry');
    fireEvent.click(retryBtn);
    expect(onRetry).toHaveBeenCalled();
  });

  it('shows error state without retry when onRetry not provided', () => {
    const error = new Error('Test error');

    render(
      <DataTable
        columns={columns}
        data={[]}
        error={error}
      />
    );

    expect(screen.getByText('Error loading data')).toBeInTheDocument();
    expect(screen.queryByText('Retry')).not.toBeInTheDocument();
  });

  it('shows empty state when no data', () => {
    render(<DataTable columns={columns} data={[]} />);

    expect(screen.getByText('No data available')).toBeInTheDocument();
  });

  it('sorts data ascending when column header clicked', () => {
    const { container } = render(
      <DataTable columns={columns} data={testData} pageSize={25} />
    );

    const headers = container.querySelectorAll('th') as NodeListOf<HTMLTableCellElement>;
    const nameHeader = headers[0];

    if (nameHeader) {
      fireEvent.click(nameHeader);

      const rows = screen.getAllByTestId('datatable-row');
      expect(rows[0]?.textContent).toContain('Alice');
      expect(rows[1]?.textContent).toContain('Bob');
      expect(rows[2]?.textContent).toContain('Charlie');
    }
  });

  it('sorts data descending on second click', () => {
    const { container } = render(
      <DataTable columns={columns} data={testData} pageSize={25} />
    );

    const headers = container.querySelectorAll('th') as NodeListOf<HTMLTableCellElement>;
    const nameHeader = headers[0];

    if (nameHeader) {
      fireEvent.click(nameHeader);
      fireEvent.click(nameHeader);

      const rows = screen.getAllByTestId('datatable-row');
      expect(rows[0]?.textContent).toContain('Charlie');
      expect(rows[1]?.textContent).toContain('Bob');
      expect(rows[2]?.textContent).toContain('Alice');
    }
  });

  it('sorts numeric columns correctly', () => {
    const { container } = render(
      <DataTable columns={columns} data={testData} pageSize={25} />
    );

    const headers = container.querySelectorAll('th') as NodeListOf<HTMLTableCellElement>;
    const valueHeader = headers[1];

    if (valueHeader) {
      fireEvent.click(valueHeader);

      const rows = screen.getAllByTestId('datatable-row');
      expect(rows[0]?.textContent).toContain('50');
      expect(rows[1]?.textContent).toContain('75');
      expect(rows[2]?.textContent).toContain('100');
    }
  });

  it('paginates data correctly', () => {
    const manyRows = Array.from({ length: 60 }, (_, i) => ({
      id: String(i),
      name: `Item ${i}`,
      value: i * 10,
    }));

    render(<DataTable columns={columns} data={manyRows} pageSize={25} />);

    expect(screen.getByText(/Page 1 of 3/)).toBeInTheDocument();

    const nextBtn = screen.getByText('Next');
    fireEvent.click(nextBtn);

    expect(screen.getByText(/Page 2 of 3/)).toBeInTheDocument();

    fireEvent.click(nextBtn);
    expect(screen.getByText(/Page 3 of 3/)).toBeInTheDocument();

    const prevBtn = screen.getByText('Prev');
    fireEvent.click(prevBtn);
    expect(screen.getByText(/Page 2 of 3/)).toBeInTheDocument();
  });

  it('disables pagination buttons at boundaries', () => {
    const manyRows = Array.from({ length: 60 }, (_, i) => ({
      id: String(i),
      name: `Item ${i}`,
      value: i * 10,
    }));

    render(<DataTable columns={columns} data={manyRows} pageSize={25} />);

    const prevBtn = screen.getByText('Prev') as HTMLButtonElement;
    expect(prevBtn).toBeDisabled();

    const nextBtn = screen.getByText('Next') as HTMLButtonElement;
    fireEvent.click(nextBtn);
    fireEvent.click(nextBtn);
    fireEvent.click(nextBtn);

    expect(nextBtn).toBeDisabled();
    expect(prevBtn).not.toBeDisabled();
  });

  it('renders with custom render function', () => {
    const customColumns: ColumnConfig<TestRow>[] = [
      { key: 'name', label: 'Name' },
      {
        key: 'value',
        label: 'Value',
        render: (v) => `$${Number(v)}`,
      },
    ];

    render(<DataTable columns={customColumns} data={testData} />);

    expect(screen.getByText('$100')).toBeInTheDocument();
    expect(screen.getByText('$50')).toBeInTheDocument();
  });

  it('shows sort indicators on sortable columns', () => {
    const { container } = render(
      <DataTable columns={columns} data={testData} pageSize={25} />
    );

    const headers = container.querySelectorAll('th') as NodeListOf<HTMLTableCellElement>;
    const nameHeader = headers[0];

    if (nameHeader) {
      expect(nameHeader.style.cursor).toBe('pointer');
      fireEvent.click(nameHeader);
      const sortIcons = nameHeader.querySelectorAll('svg');
      expect(sortIcons.length).toBeGreaterThan(0);
    }
  });

  it('renders non-sortable columns', () => {
    const nonSortColumns: ColumnConfig<TestRow>[] = [
      { key: 'name', label: 'Name', sortable: false },
      { key: 'value', label: 'Value' },
    ];

    const { container } = render(
      <DataTable columns={nonSortColumns} data={testData} pageSize={25} />
    );

    const headers = container.querySelectorAll('th') as NodeListOf<HTMLTableCellElement>;
    const nameHeader = headers[0];

    if (nameHeader) {
      fireEvent.click(nameHeader);
      const rows = screen.getAllByTestId('datatable-row');
      expect(rows[0]?.textContent).toContain('Alice');
    }
  });

  it('handles null values in sort comparison', () => {
    interface NullableRow {
      id: string;
      name: string | null;
      value: number | null;
    }

    const dataWithNulls: NullableRow[] = [
      { id: '1', name: 'Alice', value: 100 },
      { id: '2', name: null, value: 50 },
      { id: '3', name: 'Charlie', value: null },
    ];

    const columns: ColumnConfig<NullableRow>[] = [
      { key: 'name', label: 'Name', sortable: true },
      { key: 'value', label: 'Value', sortable: true },
    ];

    const { container } = render(
      <DataTable columns={columns} data={dataWithNulls} pageSize={25} />
    );

    const headers = container.querySelectorAll('th') as NodeListOf<HTMLTableCellElement>;
    const nameHeader = headers[0];

    if (nameHeader) {
      fireEvent.click(nameHeader);
      const rows = screen.getAllByTestId('datatable-row');
      expect(rows).toHaveLength(3);
    }
  });

  it('handles unknown type values in sort comparison', () => {
    interface MixedTypeRow {
      id: string;
      name: string;
      metadata: { [key: string]: unknown };
    }

    const dataWithMixed: MixedTypeRow[] = [
      { id: '1', name: 'Alice', metadata: { key: 'value' } },
      { id: '2', name: 'Bob', metadata: { key: 'other' } },
    ];

    const columns: ColumnConfig<MixedTypeRow>[] = [
      { key: 'name', label: 'Name', sortable: true },
      { key: 'metadata', label: 'Metadata', sortable: true },
    ];

    const { container } = render(
      <DataTable columns={columns} data={dataWithMixed} pageSize={25} />
    );

    const headers = container.querySelectorAll('th') as NodeListOf<HTMLTableCellElement>;
    const metadataHeader = headers[1];

    if (metadataHeader) {
      fireEvent.click(metadataHeader);
      const rows = screen.getAllByTestId('datatable-row');
      expect(rows).toHaveLength(2);
    }
  });

  it('handles sort direction toggle on same column', () => {
    const { container } = render(
      <DataTable columns={columns} data={testData} pageSize={25} />
    );

    const headers = container.querySelectorAll('th') as NodeListOf<HTMLTableCellElement>;
    const nameHeader = headers[0];

    if (nameHeader) {
      // First click - sort ascending
      fireEvent.click(nameHeader);
      let rows = screen.getAllByTestId('datatable-row');
      expect(rows[0]?.textContent).toContain('Alice');

      // Second click - sort descending
      fireEvent.click(nameHeader);
      rows = screen.getAllByTestId('datatable-row');
      expect(rows[0]?.textContent).toContain('Charlie');
    }
  });
});
