import { getIconComponent } from './icons';
import {
  Laptop,
  Zap,
  BarChart3,
  Settings,
  Clock,
  AlertCircle,
  Download,
  Upload,
  Trash2,
  Edit,
  Eye,
  EyeOff,
  Search,
  Plus,
  X,
  ChevronDown,
  ChevronUp,
  Home,
  RefreshCw,
} from 'lucide-react';

describe('getIconComponent', () => {
  it('returns correct icon for known names', () => {
    expect(getIconComponent('laptop')).toBe(Laptop);
    expect(getIconComponent('zap')).toBe(Zap);
    expect(getIconComponent('bar-chart')).toBe(BarChart3);
    expect(getIconComponent('settings')).toBe(Settings);
    expect(getIconComponent('clock')).toBe(Clock);
    expect(getIconComponent('alert-circle')).toBe(AlertCircle);
    expect(getIconComponent('download')).toBe(Download);
    expect(getIconComponent('upload')).toBe(Upload);
    expect(getIconComponent('trash')).toBe(Trash2);
    expect(getIconComponent('edit')).toBe(Edit);
    expect(getIconComponent('eye')).toBe(Eye);
    expect(getIconComponent('eye-off')).toBe(EyeOff);
    expect(getIconComponent('search')).toBe(Search);
    expect(getIconComponent('plus')).toBe(Plus);
    expect(getIconComponent('x')).toBe(X);
    expect(getIconComponent('chevron-down')).toBe(ChevronDown);
    expect(getIconComponent('chevron-up')).toBe(ChevronUp);
    expect(getIconComponent('home')).toBe(Home);
    expect(getIconComponent('refresh-cw')).toBe(RefreshCw);
  });

  it('returns Home icon for unknown names', () => {
    expect(getIconComponent('unknown-icon')).toBe(Home);
    expect(getIconComponent('invalid')).toBe(Home);
    expect(getIconComponent('')).toBe(Home);
  });

  it('handles case-sensitive icon names', () => {
    // Icon names are lowercase
    expect(getIconComponent('Laptop')).toBe(Home); // fallback for case mismatch
    expect(getIconComponent('laptop')).toBe(Laptop);
  });
});
