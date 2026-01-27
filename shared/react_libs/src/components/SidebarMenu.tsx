import React, { useState, ReactNode } from 'react';

export interface MenuItem {
  name: string;
  href: string;
  icon?: React.ComponentType<{ className?: string }>;
  roles?: string[];
}

export interface MenuCategory {
  header?: string;
  collapsible?: boolean;
  items: MenuItem[];
}

export interface SidebarColorConfig {
  // Sidebar colors
  sidebarBackground: string;
  sidebarBorder: string;

  // Header/Logo section
  logoSectionBorder: string;

  // Navigation colors
  categoryHeaderText: string;
  menuItemText: string;
  menuItemHover: string;
  menuItemActive: string;
  menuItemActiveText: string;

  // Collapse indicator
  collapseIndicator: string;

  // Footer section
  footerBorder: string;
  footerButtonText: string;
  footerButtonHover: string;

  // Scrollbar
  scrollbarTrack: string;
  scrollbarThumb: string;
  scrollbarThumbHover: string;
}

export interface SidebarMenuProps {
  logo?: ReactNode;
  categories: MenuCategory[];
  currentPath: string;
  onNavigate?: (href: string) => void;
  footerItems?: MenuItem[];
  userRole?: string;
  width?: string;
  colors?: SidebarColorConfig;
  collapseIcon?: React.ComponentType<{ className?: string }>;
  expandIcon?: React.ComponentType<{ className?: string }>;
}

// Default Elder-inspired color scheme (slate dark with blue accent)
const DEFAULT_COLORS: SidebarColorConfig = {
  sidebarBackground: 'bg-slate-800',
  sidebarBorder: 'border-slate-700',
  logoSectionBorder: 'border-slate-700',
  categoryHeaderText: 'text-slate-400',
  menuItemText: 'text-slate-300',
  menuItemHover: 'hover:bg-slate-700 hover:text-white',
  menuItemActive: 'bg-primary-600',
  menuItemActiveText: 'text-white',
  collapseIndicator: 'text-slate-400',
  footerBorder: 'border-slate-700',
  footerButtonText: 'text-slate-300',
  footerButtonHover: 'hover:bg-slate-700 hover:text-white',
  scrollbarTrack: 'bg-slate-800',
  scrollbarThumb: 'bg-slate-600',
  scrollbarThumbHover: 'hover:bg-slate-500',
};

// Default collapse/expand icons (simple chevron)
const DefaultChevronDown: React.FC<{ className?: string }> = ({ className }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
  </svg>
);

const DefaultChevronRight: React.FC<{ className?: string }> = ({ className }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor">
    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
  </svg>
);

export const SidebarMenu: React.FC<SidebarMenuProps> = ({
  logo,
  categories,
  currentPath,
  onNavigate,
  footerItems = [],
  userRole,
  width = 'w-64',
  colors,
  collapseIcon: CollapseIcon = DefaultChevronDown,
  expandIcon: ExpandIcon = DefaultChevronRight,
}) => {
  const [collapsedCategories, setCollapsedCategories] = useState<Record<string, boolean>>({});
  const theme = colors || DEFAULT_COLORS;

  const toggleCategory = (header: string) => {
    setCollapsedCategories((prev) => ({
      ...prev,
      [header]: !prev[header],
    }));
  };

  const isActive = (itemHref: string) => {
    return currentPath === itemHref || (itemHref !== '/' && currentPath.startsWith(itemHref));
  };

  const handleItemClick = (href: string) => {
    if (onNavigate) {
      onNavigate(href);
    }
  };

  const hasPermission = (item: MenuItem): boolean => {
    if (!item.roles || item.roles.length === 0) return true;
    if (!userRole) return false;
    return item.roles.includes(userRole);
  };

  return (
    <div className={`fixed inset-y-0 left-0 ${width} ${theme.sidebarBackground} border-r ${theme.sidebarBorder} flex flex-col`}>
      {/* Logo Section */}
      {logo && (
        <div className={`flex items-center justify-center h-16 px-6 border-b ${theme.logoSectionBorder}`}>
          {logo}
        </div>
      )}

      {/* Navigation - Scrollable */}
      <nav className="flex-1 px-4 py-6 overflow-y-auto">
        <style>
          {`
            nav::-webkit-scrollbar {
              width: 10px;
            }
            nav::-webkit-scrollbar-track {
              background: transparent;
            }
            nav::-webkit-scrollbar-thumb {
              background: ${theme.scrollbarThumb.replace('bg-', '#')};
              border-radius: 5px;
            }
            nav::-webkit-scrollbar-thumb:hover {
              background: ${theme.scrollbarThumbHover.replace('hover:bg-', '#')};
            }
          `}
        </style>

        <div className="space-y-6">
          {categories.map((category, categoryIndex) => {
            const isCollapsed = category.header ? collapsedCategories[category.header] : false;
            const visibleItems = category.items.filter((item) => hasPermission(item));

            if (visibleItems.length === 0) return null;

            return (
              <div key={category.header || `category-${categoryIndex}`}>
                {/* Category Header */}
                {category.header && (
                  <button
                    onClick={() => category.collapsible && toggleCategory(category.header!)}
                    className={`flex items-center justify-between w-full px-4 py-2 text-xs font-semibold uppercase tracking-wider ${theme.categoryHeaderText} ${
                      category.collapsible ? 'cursor-pointer hover:text-slate-300' : ''
                    }`}
                  >
                    <span>{category.header}</span>
                    {category.collapsible && (
                      <span className={theme.collapseIndicator}>
                        {isCollapsed ? <ExpandIcon className="w-3 h-3" /> : <CollapseIcon className="w-3 h-3" />}
                      </span>
                    )}
                  </button>
                )}

                {/* Menu Items */}
                {!isCollapsed && (
                  <div className="space-y-1 mt-2">
                    {visibleItems.map((item) => {
                      const Icon = item.icon;
                      const active = isActive(item.href);

                      return (
                        <button
                          key={item.name}
                          onClick={() => handleItemClick(item.href)}
                          className={`flex items-center w-full px-4 py-3 text-sm font-medium rounded-lg transition-colors ${
                            active
                              ? `${theme.menuItemActive} ${theme.menuItemActiveText}`
                              : `${theme.menuItemText} ${theme.menuItemHover}`
                          }`}
                        >
                          {Icon && <Icon className="w-5 h-5 mr-3 flex-shrink-0" />}
                          <span className="truncate">{item.name}</span>
                        </button>
                      );
                    })}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </nav>

      {/* Footer Section - Sticky Bottom */}
      {footerItems.length > 0 && (
        <div className={`p-4 border-t ${theme.footerBorder} space-y-1`}>
          {footerItems.filter(hasPermission).map((item) => {
            const Icon = item.icon;
            const active = isActive(item.href);

            return (
              <button
                key={item.name}
                onClick={() => handleItemClick(item.href)}
                className={`flex items-center w-full px-4 py-3 text-sm font-medium rounded-lg transition-colors ${
                  active
                    ? `${theme.menuItemActive} ${theme.menuItemActiveText}`
                    : `${theme.footerButtonText} ${theme.footerButtonHover}`
                }`}
              >
                {Icon && <Icon className="w-5 h-5 mr-3 flex-shrink-0" />}
                <span className="truncate">{item.name}</span>
              </button>
            );
          })}
        </div>
      )}
    </div>
  );
};
