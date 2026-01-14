# Web UI Design Standards

Part of [Development Standards](../STANDARDS.md)

**ALL ReactJS frontend applications MUST follow these design patterns:**

## Design Philosophy

- **Dark Theme Default**: Use dark backgrounds with light text for reduced eye strain
- **Consistent Spacing**: Use standardized spacing scale (Tailwind's spacing utilities)
- **Smooth Transitions**: Apply `transition-colors` or `transition-all 0.2s` for state changes
- **Subtle Gradients**: Use gradient accents sparingly for modern aesthetic
- **Responsive Design**: Mobile-first approach with breakpoint-based layouts

## Color Palette (Dark Theme)

**CSS Variables (Required):**
```css
:root {
  /* Background colors */
  --bg-primary: #0f172a;      /* slate-900 - main background */
  --bg-secondary: #1e293b;    /* slate-800 - sidebar/cards */
  --bg-tertiary: #334155;     /* slate-700 - hover states */

  /* Text colors - Gold default */
  --text-primary: #fbbf24;    /* amber-400 - headings, primary text */
  --text-secondary: #f59e0b;  /* amber-500 - body text */
  --text-muted: #d97706;      /* amber-600 - secondary/muted text */
  --text-light: #fef3c7;      /* amber-100 - high contrast text */

  /* Accent colors (sky-blue for interactive elements) */
  --primary-400: #38bdf8;
  --primary-500: #0ea5e9;
  --primary-600: #0284c7;
  --primary-700: #0369a1;

  /* Border colors */
  --border-color: #334155;    /* slate-700 */

  /* Admin/Warning accent */
  --warning-color: #eab308;   /* yellow-500 */
}
```

**Gold Text Usage:**
- Default body text: `text-amber-400` or `var(--text-primary)`
- Headings: `text-amber-400` with `font-semibold`
- Muted/secondary text: `text-amber-600` or `var(--text-muted)`
- High contrast when needed: `text-amber-100` or `var(--text-light)`
- Interactive elements (links, buttons): Use primary blue accent for distinction

## Sidebar Navigation Pattern (Elder Style)

**Required for applications with complex navigation:**

**Structure:**
```
┌─────────────────────────────────────────────────────────────┐
│  Logo Section (h-16, centered)                              │
├─────────────────────────────────────────────────────────────┤
│  Primary Navigation (always visible)                        │
│    ├── Dashboard                                            │
│    ├── Search                                               │
│    └── Overview                                             │
├─────────────────────────────────────────────────────────────┤
│  Category: Assets (collapsible)           [▼]               │
│    ├── Entities                                             │
│    ├── Organizations                                        │
│    └── Services                                             │
├─────────────────────────────────────────────────────────────┤
│  Category: Settings (collapsible)         [▶]               │
│    └── (collapsed)                                          │
├─────────────────────────────────────────────────────────────┤
│  Admin Section (role-based, yellow accent)                  │
│    └── System Settings                                      │
├─────────────────────────────────────────────────────────────┤
│  User Section (bottom, border-top)                          │
│    ├── Profile                                              │
│    └── Logout                                               │
└─────────────────────────────────────────────────────────────┘
```

**Implementation Requirements:**

1. **Fixed Positioning**: Sidebar fixed to left edge, full height
   ```jsx
   <div className="fixed inset-y-0 left-0 w-64 bg-slate-800 border-r border-slate-700">
   ```

2. **Collapsible Categories**: State-managed category groups
   ```typescript
   const [collapsedCategories, setCollapsedCategories] = useState<Record<string, boolean>>({})

   const toggleCategory = (header: string) => {
     setCollapsedCategories(prev => ({
       ...prev,
       [header]: !prev[header]
     }))
   }
   ```

3. **Navigation Item Styling**:
   ```jsx
   <Link
     to={item.href}
     className={`flex items-center px-4 py-3 text-sm font-medium rounded-lg transition-colors ${
       isActive
         ? 'bg-primary-600 text-white'
         : 'text-amber-400 hover:bg-slate-700 hover:text-amber-200'
     }`}
   >
     <Icon className="w-5 h-5 mr-3" />
     {item.name}
   </Link>
   ```

4. **Active Route Detection**:
   ```typescript
   const isActive = location.pathname === item.href ||
                    location.pathname.startsWith(item.href + '/')
   ```

5. **Admin Items** (role-based with yellow accent):
   ```jsx
   className={isActive
     ? 'bg-yellow-600/20 text-yellow-500 border border-yellow-600/30'
     : 'text-amber-400 hover:bg-slate-700 hover:text-amber-200'}
   ```

6. **Main Content Offset**: Match sidebar width
   ```jsx
   <div className="pl-64">
     <main className="min-h-screen">
       <Outlet />
     </main>
   </div>
   ```

7. **Icons**: Use `lucide-react` with consistent sizing (`w-5 h-5`)

## Tab Navigation Pattern (WaddlePerf Style)

**Required for applications with content sections:**

**Structure:**
```
┌─────────────────────────────────────────────────────────────┐
│  [Speed Test]  [Network Tests]  [Trace Tests]  [Download]   │
│  ━━━━━━━━━━━━                                               │
│  (active tab has colored underline)                         │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│                    Tab Content Area                         │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

**Implementation Requirements:**

1. **Tab Container Styling**:
   ```css
   .tab-navigation {
     display: flex;
     gap: 1rem;
     margin-bottom: 2rem;
     border-bottom: 2px solid var(--border-color);
   }
   ```

2. **Tab Button Styling**:
   ```css
   .tab-button {
     padding: 0.75rem 1.5rem;
     background: transparent;
     border: none;
     border-bottom: 3px solid transparent;
     color: var(--text-secondary);    /* amber-500 - gold default */
     font-size: 1rem;
     font-weight: 500;
     cursor: pointer;
     transition: all 0.2s;
     margin-bottom: -2px;  /* Overlap container border */
   }

   .tab-button:hover {
     color: var(--text-light);        /* amber-100 - lighter gold on hover */
   }

   .tab-button.active {
     color: var(--primary-500);       /* sky-blue for active distinction */
     border-bottom-color: var(--primary-500);
     font-weight: 600;
   }
   ```

3. **React Implementation**:
   ```typescript
   type TabKey = 'overview' | 'details' | 'settings' | 'logs'
   const [activeTab, setActiveTab] = useState<TabKey>('overview')

   // Tab navigation
   <div className="tab-navigation">
     {tabs.map(tab => (
       <button
         key={tab.key}
         className={`tab-button ${activeTab === tab.key ? 'active' : ''}`}
         onClick={() => setActiveTab(tab.key)}
       >
         {tab.label}
       </button>
     ))}
   </div>

   // Tab content (conditional rendering)
   {activeTab === 'overview' && <OverviewPanel />}
   {activeTab === 'details' && <DetailsPanel />}
   {activeTab === 'settings' && <SettingsPanel />}
   {activeTab === 'logs' && <LogsPanel />}
   ```

4. **Transition Details**:
   - Duration: 200ms (0.2s)
   - Properties: color, border-bottom-color
   - Easing: linear (default)

5. **Dark Mode Support**: Use CSS variables for all colors

## Combined Layout Pattern

**For applications requiring both sidebar and tabs:**

```
┌──────────────┬──────────────────────────────────────────────┐
│              │  Page Header                                 │
│   SIDEBAR    ├──────────────────────────────────────────────┤
│              │  [Tab 1]  [Tab 2]  [Tab 3]  [Tab 4]          │
│  - Primary   │  ━━━━━━━                                     │
│  - Assets    ├──────────────────────────────────────────────┤
│  - Settings  │                                              │
│  - Admin     │           Tab Content Area                   │
│              │                                              │
│  ──────────  │                                              │
│  Profile     │                                              │
│  Logout      │                                              │
└──────────────┴──────────────────────────────────────────────┘
```

**Layout Structure:**
```jsx
<div className="flex min-h-screen">
  {/* Sidebar - fixed left */}
  <aside className="fixed inset-y-0 left-0 w-64 bg-slate-800 border-r border-slate-700">
    <Sidebar />
  </aside>

  {/* Main content - offset for sidebar */}
  <main className="flex-1 pl-64">
    <div className="p-6">
      {/* Page header - gold text */}
      <h1 className="text-2xl font-semibold text-amber-400 mb-6">Page Title</h1>

      {/* Tab navigation */}
      <TabNavigation activeTab={activeTab} onTabChange={setActiveTab} />

      {/* Tab content */}
      <div className="mt-6">
        {renderTabContent()}
      </div>
    </div>
  </main>
</div>
```

## Right Sidebar Pattern (Detail Pages)

**For detail pages with metadata panels:**

```jsx
<div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
  {/* Main content */}
  <div className="lg:col-span-2">
    <MainContent />
  </div>

  {/* Right sidebar */}
  <div className="lg:col-span-1 space-y-6">
    <Card title="Related Items">
      <RelatedItemsList />
    </Card>
    <Card title="Metadata">
      <MetadataPanel />
    </Card>
  </div>
</div>
```

## Required Dependencies

```json
{
  "dependencies": {
    "lucide-react": "^0.453.0",
    "react-router-dom": "^6.20.0",
    "@tanstack/react-query": "^5.0.0"
  },
  "devDependencies": {
    "tailwindcss": "^4.0.0",
    "@tailwindcss/postcss": "^4.0.0"
  }
}
```

## Tailwind CSS v4 Theme Configuration

```css
/* index.css */
@import "tailwindcss";

@theme {
  --color-primary-50: #f0f9ff;
  --color-primary-100: #e0f2fe;
  --color-primary-200: #bae6fd;
  --color-primary-300: #7dd3fc;
  --color-primary-400: #38bdf8;
  --color-primary-500: #0ea5e9;
  --color-primary-600: #0284c7;
  --color-primary-700: #0369a1;
  --color-primary-800: #075985;
  --color-primary-900: #0c4a6e;
}
```

## Component Library Standards

**Card Component:**
```jsx
export const Card = ({ title, children, className = '' }) => (
  <div className={`bg-slate-800 border border-slate-700 rounded-lg shadow-lg ${className}`}>
    {title && (
      <div className="px-4 py-3 border-b border-slate-700">
        <h3 className="text-sm font-semibold text-amber-400">{title}</h3>
      </div>
    )}
    <div className="p-4 text-amber-400">{children}</div>
  </div>
)
```

**Button Component:**
```jsx
const variants = {
  primary: 'bg-primary-600 hover:bg-primary-700 text-white',
  secondary: 'bg-slate-700 hover:bg-slate-600 text-amber-400',
  danger: 'bg-red-600 hover:bg-red-700 text-white',
  ghost: 'bg-transparent hover:bg-slate-700 text-amber-400 hover:text-amber-200'
}

export const Button = ({ variant = 'primary', size = 'md', children, ...props }) => (
  <button
    className={`rounded-lg font-medium transition-colors ${variants[variant]} ${sizes[size]}`}
    {...props}
  >
    {children}
  </button>
)
```

## Accessibility Requirements

1. **Keyboard Navigation**: All interactive elements must be keyboard accessible
2. **Focus States**: Visible focus indicators using `focus:ring-2 focus:ring-primary-500`
3. **ARIA Labels**: Proper labeling for screen readers
4. **Color Contrast**: Minimum 4.5:1 contrast ratio for text
5. **Reduced Motion**: Respect `prefers-reduced-motion` preference
