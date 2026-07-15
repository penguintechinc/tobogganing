import React from 'react';
import { render, screen } from '@testing-library/react';
import { PlaceholderView } from './PlaceholderView';

describe('PlaceholderView', () => {
  it('renders module and view names', () => {
    render(<PlaceholderView module="analytics" view="dashboard" />);

    expect(screen.getByText('Dashboard')).toBeInTheDocument();
    expect(screen.getByText('Module: analytics')).toBeInTheDocument();
  });

  it('capitalizes view name', () => {
    render(<PlaceholderView module="reports" view="usage" />);

    expect(screen.getByText('Usage')).toBeInTheDocument();
  });

  it('displays coming soon message', () => {
    render(<PlaceholderView module="admin" view="settings" />);

    expect(screen.getByText(/implementation coming soon/i)).toBeInTheDocument();
  });

  it('renders with correct styling container', () => {
    const { container } = render(<PlaceholderView module="test" view="view" />);

    const placeholderDiv = container.querySelector('.bg-slate-800');
    expect(placeholderDiv).toBeInTheDocument();
  });

  it('handles multi-word view names', () => {
    render(<PlaceholderView module="analytics" view="user-behavior" />);

    expect(screen.getByText('User-behavior')).toBeInTheDocument();
  });
});
