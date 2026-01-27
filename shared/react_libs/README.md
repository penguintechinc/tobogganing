# @penguin/react_libs

Shared React components and utilities for Penguin Tech Inc projects.

## Installation

```bash
npm install @penguin/react_libs
# or
yarn add @penguin/react_libs
```

## Components

### FormModalBuilder

A flexible, reusable form modal builder that handles various input types with built-in validation.

#### Features

- 📝 Support for 14+ input types (text, email, password, number, select, checkbox, etc.)
- 📑 **Automatic tabs** - Creates tabs when field count exceeds threshold (default: 8 fields)
- 🎛️ **Manual tab control** - Organize fields by category using `tab` property or explicit tab configuration
- 🔄 **Next/Previous navigation** - Multi-step form workflow with tab navigation
- ⚠️ **Tab error indicators** - Visual indicators show which tabs have validation errors
- ✅ Built-in validation with custom validators
- 🎨 **Comprehensive theming** - Full color customization for all elements
- 🌙 **Dark mode default** - Beautiful navy & gold dark theme out of the box
- 🎨 Customizable styling (background color, width, z-index)
- 📱 Responsive design with Tailwind CSS
- ⚡ TypeScript support with full type safety
- 🔄 Async form submission handling
- 📏 No scrollbars needed - Tabs keep forms clean and organized
- 🎯 Required field indicators
- ⚠️ Field-level error messages

#### Basic Usage

```tsx
import { useState } from 'react';
import { FormModalBuilder, FormField } from '@penguin/react_libs';

function MyComponent() {
  const [isOpen, setIsOpen] = useState(false);

  const fields: FormField[] = [
    {
      name: 'username',
      type: 'text',
      label: 'Username',
      description: 'Choose a unique username',
      required: true,
      placeholder: 'Enter username',
    },
    {
      name: 'email',
      type: 'email',
      label: 'Email Address',
      required: true,
    },
    {
      name: 'age',
      type: 'number',
      label: 'Age',
      min: 18,
      max: 120,
    },
  ];

  const handleSubmit = async (data: Record<string, any>) => {
    console.log('Form data:', data);
    // Make API call here
    await fetch('/api/users', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    });
  };

  return (
    <>
      <button onClick={() => setIsOpen(true)}>Open Form</button>

      <FormModalBuilder
        title="Create New User"
        fields={fields}
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        onSubmit={handleSubmit}
        submitButtonText="Create User"
        width="lg"
      />
    </>
  );
}
```

#### Advanced Usage with Custom Validation

```tsx
const fields: FormField[] = [
  {
    name: 'password',
    type: 'password',
    label: 'Password',
    required: true,
    validation: (value) => {
      if (value.length < 8) {
        return 'Password must be at least 8 characters';
      }
      if (!/[A-Z]/.test(value)) {
        return 'Password must contain at least one uppercase letter';
      }
      return null;
    },
  },
  {
    name: 'role',
    type: 'select',
    label: 'Role',
    required: true,
    options: [
      { value: 'admin', label: 'Administrator' },
      { value: 'maintainer', label: 'Maintainer' },
      { value: 'viewer', label: 'Viewer' },
    ],
  },
  {
    name: 'notifications',
    type: 'checkbox',
    label: 'Enable email notifications',
    defaultValue: true,
  },
];
```

#### Tabbed Modal Windows

The FormModalBuilder **automatically creates tabs** when your form exceeds 8 fields (default threshold). This eliminates scrollbars and provides a clean, multi-step form experience.

**Automatic Tabs (12+ fields):**
```tsx
// With 12 fields, tabs are auto-generated: "General" and "Step 2"
const fields: FormField[] = [
  // ... 12 fields defined here
];

<FormModalBuilder
  title="User Registration"
  fields={fields}
  isOpen={isOpen}
  onClose={() => setIsOpen(false)}
  onSubmit={handleSubmit}
  // Tabs auto-created! Default: 8 field threshold, 6 fields per tab
/>
```

**Manual Tab Assignment:**
```tsx
// Organize fields by category using the 'tab' property
const fields: FormField[] = [
  { name: 'firstName', type: 'text', label: 'First Name', tab: 'Personal Info' },
  { name: 'lastName', type: 'text', label: 'Last Name', tab: 'Personal Info' },
  { name: 'username', type: 'text', label: 'Username', tab: 'Account' },
  { name: 'password', type: 'password', label: 'Password', tab: 'Account' },
  { name: 'notifications', type: 'checkbox', label: 'Email Alerts', tab: 'Preferences' },
];

<FormModalBuilder
  title="Create Account"
  fields={fields}  // Tabs auto-organized by field.tab!
  isOpen={isOpen}
  onClose={() => setIsOpen(false)}
  onSubmit={handleSubmit}
/>
```

**Explicit Tab Configuration:**
```tsx
import { FormTab } from '@penguin/react_libs';

const tabs: FormTab[] = [
  {
    id: 'basic',
    label: 'Basic Info',
    fields: [
      { name: 'name', type: 'text', label: 'Product Name', required: true },
      { name: 'price', type: 'number', label: 'Price', required: true },
    ],
  },
  {
    id: 'inventory',
    label: 'Inventory',
    fields: [
      { name: 'stock', type: 'number', label: 'Stock', required: true },
      { name: 'supplier', type: 'text', label: 'Supplier' },
    ],
  },
];

const allFields = tabs.flatMap((tab) => tab.fields);

<FormModalBuilder
  title="Add Product"
  fields={allFields}
  tabs={tabs}  // Explicit tab control
  isOpen={isOpen}
  onClose={() => setIsOpen(false)}
  onSubmit={handleSubmit}
/>
```

**Custom Threshold:**
```tsx
<FormModalBuilder
  fields={fields}
  autoTabThreshold={5}  // Create tabs if more than 5 fields
  fieldsPerTab={4}      // Put 4 fields per tab
  // ... other props
/>
```

**Tab Features:**
- 📑 Automatic tab creation prevents scrollbar overflow
- 🔄 Next/Previous buttons for multi-step workflow
- ⚠️ Visual error indicators on tabs with validation errors
- ✨ Automatic navigation to first tab with errors on submit
- 🎯 Last tab shows "Submit" button instead of "Next"

#### Comprehensive Theming

The FormModalBuilder supports complete color customization for all UI elements, with a **dark mode navy & gold theme as the default**.

**Default Dark Mode (Navy & Gold):**
```tsx
// No colors prop needed - beautiful dark mode out of the box!
<FormModalBuilder
  title="Create Account"
  fields={fields}
  isOpen={isOpen}
  onClose={() => setIsOpen(false)}
  onSubmit={handleSubmit}
  // Defaults to navy background with gold accents
/>
```

**Custom Light Mode:**
```tsx
import { ColorConfig } from '@penguin/react_libs';

const lightTheme: ColorConfig = {
  modalBackground: 'bg-white',
  headerBackground: 'bg-white',
  footerBackground: 'bg-gray-50',
  overlayBackground: 'bg-gray-500 bg-opacity-75',
  titleText: 'text-gray-900',
  labelText: 'text-gray-700',
  descriptionText: 'text-gray-500',
  errorText: 'text-red-600',
  buttonText: 'text-white',
  fieldBackground: 'bg-white',
  fieldBorder: 'border-gray-300',
  fieldText: 'text-gray-900',
  fieldPlaceholder: 'placeholder-gray-400',
  focusRing: 'focus:ring-blue-500',
  focusBorder: 'focus:border-blue-500',
  primaryButton: 'bg-blue-600',
  primaryButtonHover: 'hover:bg-blue-700',
  secondaryButton: 'bg-white',
  secondaryButtonHover: 'hover:bg-gray-50',
  secondaryButtonBorder: 'border-gray-300',
  activeTab: 'text-blue-600',
  activeTabBorder: 'border-blue-500',
  inactiveTab: 'text-gray-500',
  inactiveTabHover: 'hover:text-gray-700 hover:border-gray-300',
  tabBorder: 'border-gray-200',
  errorTabText: 'text-red-600',
  errorTabBorder: 'border-red-300',
};

<FormModalBuilder
  colors={lightTheme}
  // ... other props
/>
```

**Default Theme Colors:**
- Background: Navy (slate-800/900)
- Text: Gold (amber-300/400)
- Fields: White backgrounds with slate borders
- Buttons: Gold primary, slate secondary
- Focus Rings: Gold (amber-500)
- Tabs: Gold active, slate inactive

**Customizable Color Properties:**
| Property | Description | Example |
|----------|-------------|---------|
| `modalBackground` | Main modal background | `bg-slate-800` |
| `headerBackground` | Header section background | `bg-slate-800` |
| `footerBackground` | Footer section background | `bg-slate-900` |
| `overlayBackground` | Backdrop overlay | `bg-gray-900 bg-opacity-75` |
| `titleText` | Modal title color | `text-amber-400` |
| `labelText` | Field label color | `text-amber-300` |
| `descriptionText` | Help text color | `text-slate-400` |
| `errorText` | Error message color | `text-red-400` |
| `buttonText` | Button text color | `text-slate-900` |
| `fieldBackground` | Input field background | `bg-white` |
| `fieldBorder` | Input field border | `border-slate-600` |
| `fieldText` | Input text color | `text-slate-900` |
| `fieldPlaceholder` | Placeholder text color | `placeholder-slate-500` |
| `focusRing` | Focus ring color | `focus:ring-amber-500` |
| `focusBorder` | Focus border color | `focus:border-amber-500` |
| `primaryButton` | Primary button background | `bg-amber-500` |
| `primaryButtonHover` | Primary button hover | `hover:bg-amber-600` |
| `secondaryButton` | Secondary button background | `bg-slate-700` |
| `secondaryButtonHover` | Secondary button hover | `hover:bg-slate-600` |
| `secondaryButtonBorder` | Secondary button border | `border-slate-600` |
| `activeTab` | Active tab text color | `text-amber-400` |
| `activeTabBorder` | Active tab border | `border-amber-500` |
| `inactiveTab` | Inactive tab text | `text-slate-400` |
| `inactiveTabHover` | Inactive tab hover | `hover:text-slate-300` |
| `tabBorder` | Tab section border | `border-slate-700` |
| `errorTabText` | Error tab text | `text-red-400` |
| `errorTabBorder` | Error tab border | `border-red-500` |

See `examples/ThemedFormExample.tsx` for complete theming examples including purple/pink, emerald green, and light mode themes.

#### Field Types

| Type | Description | Additional Props |
|------|-------------|------------------|
| `text` | Standard text input | `placeholder`, `pattern` |
| `email` | Email input with validation | `placeholder` |
| `password` | Password input | `placeholder` |
| `number` | Number input | `min`, `max` |
| `tel` | Telephone input | `pattern` |
| `url` | URL input with validation | `placeholder` |
| `textarea` | Multi-line text input | `rows`, `placeholder` |
| `select` | Dropdown selection | `options` (required) |
| `checkbox` | Single checkbox | `defaultValue` |
| `radio` | Radio button group | `options` (required) |
| `date` | Date picker | - |
| `time` | Time picker | - |
| `datetime-local` | Date and time picker | - |
| `file` | File upload | `accept` |

#### Props

```typescript
interface FormModalBuilderProps {
  title: string;                    // Modal title
  fields: FormField[];              // Array of form fields
  tabs?: FormTab[];                 // Optional explicit tab configuration
  isOpen: boolean;                  // Controls modal visibility
  onClose: () => void;              // Close handler
  onSubmit: (data: Record<string, any>) => Promise<void> | void;  // Submit handler
  submitButtonText?: string;        // Submit button text (default: "Submit")
  cancelButtonText?: string;        // Cancel button text (default: "Cancel")
  width?: 'sm' | 'md' | 'lg' | 'xl' | '2xl';  // Modal width (default: "md")
  backgroundColor?: string;         // Background color class (default: "bg-white")
  maxHeight?: string;               // Max height class (default: "max-h-[80vh]")
  zIndex?: number;                  // Z-index for modal (default: 9999)
  autoTabThreshold?: number;        // Auto-create tabs if fields > threshold (default: 8)
  fieldsPerTab?: number;            // Fields per auto-generated tab (default: 6)
}
```

#### FormField Interface

```typescript
interface FormField {
  name: string;                     // Field identifier (unique)
  type: string;                     // Input type (see Field Types above)
  label: string;                    // Display label
  description?: string;             // Optional help text
  defaultValue?: string | number | boolean;  // Default value
  placeholder?: string;             // Placeholder text
  required?: boolean;               // Mark as required
  options?: Array<{ value: string | number; label: string }>;  // For select/radio
  min?: number;                     // Min value (number fields)
  max?: number;                     // Max value (number fields)
  pattern?: string;                 // Regex pattern for validation
  accept?: string;                  // File types (file fields)
  rows?: number;                    // Rows for textarea
  validation?: (value: any) => string | null;  // Custom validator
  tab?: string;                     // Tab name for manual tab assignment
}

interface FormTab {
  id: string;                       // Unique tab identifier
  label: string;                    // Tab display label
  fields: FormField[];              // Fields in this tab
}
```

#### Customization Examples

**Custom Background Color:**
```tsx
<FormModalBuilder
  backgroundColor="bg-gray-50"
  // ... other props
/>
```

**Custom Width and Height:**
```tsx
<FormModalBuilder
  width="2xl"
  maxHeight="max-h-[90vh]"
  // ... other props
/>
```

**Custom Z-Index:**
```tsx
<FormModalBuilder
  zIndex={10000}
  // ... other props
/>
```

### SidebarMenu

A collapsible sidebar navigation component inspired by Elder's sidebar, with role-based permissions and full theme customization.

#### Features

- 📂 Collapsible category sections
- 🔒 Role-based menu item visibility
- 🎨 **Comprehensive theming** - Full color customization for all elements
- 🌙 **Elder-inspired default** - Slate dark theme with blue accent
- 🎯 Active item highlighting with flexible path matching
- 🔄 Navigation callback system
- ✨ Customizable collapse/expand icons
- 📏 Configurable sidebar width
- 🎨 Sticky footer section for profile/logout items
- 🖱️ Smooth hover states and transitions
- 📱 Fixed sidebar with scrollable navigation area

#### Basic Usage

```tsx
import { useState } from 'react';
import { SidebarMenu, MenuCategory, MenuItem } from '@penguin/react_libs';

function MyApp() {
  const [currentPath, setCurrentPath] = useState('/');

  const categories: MenuCategory[] = [
    {
      items: [
        { name: 'Dashboard', href: '/', icon: DashboardIcon },
      ],
    },
    {
      header: 'Management',
      collapsible: true,
      items: [
        { name: 'Users', href: '/users', icon: UsersIcon },
        { name: 'Teams', href: '/teams', icon: UsersIcon },
      ],
    },
  ];

  const footerItems: MenuItem[] = [
    { name: 'Profile', href: '/profile', icon: ProfileIcon },
    { name: 'Logout', href: '/logout', icon: LogoutIcon },
  ];

  return (
    <div className="h-screen">
      <SidebarMenu
        logo={<img src="/logo.png" alt="Logo" className="h-12 w-auto" />}
        categories={categories}
        currentPath={currentPath}
        onNavigate={setCurrentPath}
        footerItems={footerItems}
        userRole="admin"
      />

      {/* Main content */}
      <div className="pl-64">
        <main className="p-8">
          <h1>Current Page: {currentPath}</h1>
        </main>
      </div>
    </div>
  );
}
```

#### Role-Based Access Control

```tsx
const categories: MenuCategory[] = [
  {
    header: 'Administration',
    collapsible: true,
    items: [
      {
        name: 'Settings',
        href: '/admin/settings',
        icon: SettingsIcon,
        roles: ['admin']  // Only visible to admin users
      },
      {
        name: 'Audit Logs',
        href: '/admin/audit',
        icon: LogIcon,
        roles: ['admin', 'maintainer']  // Visible to admin and maintainer
      },
    ],
  },
];

<SidebarMenu
  categories={categories}
  userRole="admin"  // Current user's role
  // ... other props
/>
```

#### Comprehensive Theming

The SidebarMenu supports complete color customization with **Elder's slate dark theme as the default**.

**Default Elder Theme:**
```tsx
// No colors prop needed - Elder theme out of the box!
<SidebarMenu
  logo={<span className="text-xl font-bold text-slate-300">App</span>}
  categories={categories}
  currentPath={currentPath}
  onNavigate={setCurrentPath}
  // Defaults to Elder's slate-800 background with primary-600 accent
/>
```

**Custom Navy & Gold Theme:**
```tsx
import { SidebarColorConfig } from '@penguin/react_libs';

const navyGoldTheme: SidebarColorConfig = {
  sidebarBackground: 'bg-slate-900',
  sidebarBorder: 'border-slate-700',
  logoSectionBorder: 'border-slate-700',
  categoryHeaderText: 'text-amber-400',
  menuItemText: 'text-amber-300',
  menuItemHover: 'hover:bg-slate-800 hover:text-amber-200',
  menuItemActive: 'bg-amber-500',
  menuItemActiveText: 'text-slate-900',
  collapseIndicator: 'text-amber-400',
  footerBorder: 'border-slate-700',
  footerButtonText: 'text-amber-300',
  footerButtonHover: 'hover:bg-slate-800 hover:text-amber-200',
  scrollbarTrack: 'bg-slate-900',
  scrollbarThumb: 'bg-slate-700',
  scrollbarThumbHover: 'hover:bg-slate-600',
};

<SidebarMenu
  colors={navyGoldTheme}
  // ... other props
/>
```

**Default Theme Colors:**
- Background: Slate dark (slate-800)
- Text: Slate light (slate-300/400)
- Active Item: Primary blue (primary-600)
- Borders: Slate (slate-700)
- Hover: Slate (slate-700) with white text

**Customizable Color Properties:**
| Property | Description | Example |
|----------|-------------|---------|
| `sidebarBackground` | Main sidebar background | `bg-slate-800` |
| `sidebarBorder` | Right border of sidebar | `border-slate-700` |
| `logoSectionBorder` | Logo section bottom border | `border-slate-700` |
| `categoryHeaderText` | Category header text color | `text-slate-400` |
| `menuItemText` | Menu item text color | `text-slate-300` |
| `menuItemHover` | Menu item hover state | `hover:bg-slate-700 hover:text-white` |
| `menuItemActive` | Active menu item background | `bg-primary-600` |
| `menuItemActiveText` | Active menu item text | `text-white` |
| `collapseIndicator` | Collapse/expand icon color | `text-slate-400` |
| `footerBorder` | Footer section top border | `border-slate-700` |
| `footerButtonText` | Footer button text | `text-slate-300` |
| `footerButtonHover` | Footer button hover | `hover:bg-slate-700 hover:text-white` |
| `scrollbarTrack` | Scrollbar track background | `bg-slate-800` |
| `scrollbarThumb` | Scrollbar thumb color | `bg-slate-600` |
| `scrollbarThumbHover` | Scrollbar thumb hover | `hover:bg-slate-500` |

See `examples/SidebarMenuExample.tsx` for complete theming examples including navy/gold, emerald green, and light mode themes.

#### Custom Icons

**Menu Item Icons:**
```tsx
import { Home, Users, Settings } from 'lucide-react';

const categories: MenuCategory[] = [
  {
    items: [
      { name: 'Dashboard', href: '/', icon: Home },
      { name: 'Users', href: '/users', icon: Users },
      { name: 'Settings', href: '/settings', icon: Settings },
    ],
  },
];
```

**Collapse/Expand Icons:**
```tsx
import { ChevronDown, ChevronRight } from 'lucide-react';

<SidebarMenu
  collapseIcon={ChevronDown}
  expandIcon={ChevronRight}
  // ... other props
/>
```

#### Props

```typescript
interface SidebarMenuProps {
  logo?: ReactNode;                  // Logo element (image, text, etc.)
  categories: MenuCategory[];        // Menu categories and items
  currentPath: string;               // Current active path
  onNavigate?: (href: string) => void;  // Navigation callback
  footerItems?: MenuItem[];          // Footer menu items (profile, logout, etc.)
  userRole?: string;                 // Current user role for permissions
  width?: string;                    // Sidebar width class (default: "w-64")
  colors?: SidebarColorConfig;       // Custom color configuration
  collapseIcon?: React.ComponentType<{ className?: string }>;  // Collapse icon
  expandIcon?: React.ComponentType<{ className?: string }>;    // Expand icon
}
```

#### MenuItem Interface

```typescript
interface MenuItem {
  name: string;                      // Display name
  href: string;                      // Navigation path
  icon?: React.ComponentType<{ className?: string }>;  // Optional icon
  roles?: string[];                  // Required roles (if any)
}
```

#### MenuCategory Interface

```typescript
interface MenuCategory {
  header?: string;                   // Category header text (optional)
  collapsible?: boolean;             // Allow collapse/expand
  items: MenuItem[];                 // Menu items in category
}
```

#### Active Item Detection

The sidebar automatically highlights the active item based on the current path:

- Exact match: `currentPath === item.href`
- Prefix match: `currentPath.startsWith(item.href)` (except for root `/`)

**Example:**
```tsx
// Current path: /users/123
// Active items:
// - { href: '/users' }          ✓ Active (prefix match)
// - { href: '/users/123' }      ✓ Active (exact match)
// - { href: '/' }               ✗ Not active (root exception)
```

#### Customization Examples

**Custom Width:**
```tsx
<SidebarMenu
  width="w-80"  // Wider sidebar
  // ... other props
/>
```

**Without Logo Section:**
```tsx
<SidebarMenu
  // No logo prop = no logo section rendered
  categories={categories}
  // ... other props
/>
```

**Without Footer:**
```tsx
<SidebarMenu
  // No footerItems or footerItems=[] = no footer section
  categories={categories}
  // ... other props
/>
```

## Development

```bash
# Install dependencies
npm install

# Build
npm run build

# Watch mode
npm run build:watch

# Lint
npm run lint

# Format
npm run format

# Type check
npm run typecheck
```

## License

AGPL-3.0 - See LICENSE file for details

## Author

Penguin Tech Inc <dev@penguintech.io>
