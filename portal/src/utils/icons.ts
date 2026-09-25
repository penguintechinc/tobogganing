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
  Globe,
  Server,
  LucideIcon,
} from 'lucide-react';

type IconName = string;

const iconMap: Record<IconName, LucideIcon> = {
  laptop: Laptop,
  zap: Zap,
  'bar-chart': BarChart3,
  settings: Settings,
  clock: Clock,
  'alert-circle': AlertCircle,
  download: Download,
  upload: Upload,
  trash: Trash2,
  edit: Edit,
  eye: Eye,
  'eye-off': EyeOff,
  search: Search,
  plus: Plus,
  x: X,
  'chevron-down': ChevronDown,
  'chevron-up': ChevronUp,
  home: Home,
  'refresh-cw': RefreshCw,
  globe: Globe,
  server: Server,
};

export function getIconComponent(name: IconName) {
  return iconMap[name] || Home;
}
