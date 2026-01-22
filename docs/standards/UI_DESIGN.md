# 🎨 UI Design Guide - Making Things Look Good

Part of [Development Standards](../STANDARDS.md)

Welcome! Building beautiful, accessible UIs doesn't have to be complicated. This guide gives you everything you need to create consistent, stunning interfaces that developers and users will love. **All ReactJS frontend applications MUST follow these patterns.**

---

## 🤔 Our Design Philosophy

We believe great UI is about respect: respect for user time, respect for eyeballs, and respect for accessibility. Here's what that means in practice:

- **Dark Wins** 💪 - Dark backgrounds with gold text reduce eye strain. Your users will code for hours. Be nice to their eyes.
- **Spacing Matters** 📏 - Consistent spacing makes things feel intentional and organized. Use Tailwind's spacing utilities religiously.
- **Smooth, Not Jarring** 🎬 - Transitions should feel natural. 200ms is your friend. `transition-colors` and `transition-all 0.2s` are essentials.
- **Gradients are Accents** ✨ - Use them sparingly for that premium feel, not everywhere.
- **Mobile-First Always** 📱 - Build for phones first, then enhance for bigger screens.

---

## 🎭 Color Palette (Dark Theme)

Our color scheme combines **dark backgrounds** with **gold accents** and **sky-blue highlights**. It's modern, comfortable, and totally professional.

### CSS Variables (Copy This!)

```css
:root {
  /* Background colors - Nice and dark */
  --bg-primary: #0f172a;      /* Darkest: main background */
  --bg-secondary: #1e293b;    /* Dark: sidebars & cards */
  --bg-tertiary: #334155;     /* Medium dark: hover states */

  /* Text colors - Beautiful gold default */
  --text-primary: #fbbf24;    /* Amber-400: headings & primary text */
  --text-secondary: #f59e0b;  /* Amber-500: body text & descriptions */
  --text-muted: #d97706;      /* Amber-600: secondary/muted info */
  --text-light: #fef3c7;      /* Amber-100: high contrast when needed */

  /* Accent colors - Sky blue for interactive elements */
  --primary-400: #38bdf8;     /* Bright blue for highlights */
  --primary-500: #0ea5e9;     /* Main interactive blue */
  --primary-600: #0284c7;     /* Blue for active/pressed states */
  --primary-700: #0369a1;     /* Darkest blue for hover/focus */

  /* Borders and subtle elements */
  --border-color: #334155;    /* Medium dark slate */

  /* Warnings and admin features */
  --warning-color: #eab308;   /* Yellow for admin/warnings */
}
```

### Color Usage Quick Guide

| Element | Color | Hex | When |
|---------|-------|-----|------|
| Page Headings | `text-amber-400` | #fbbf24 | Main titles |
| Body Text | `text-amber-400` | #fbbf24 | All paragraph text (default) |
| Secondary Text | `text-amber-600` | #d97706 | Help text, descriptions |
| High Contrast | `text-amber-100` | #fef3c7 | Subtle text on dark backgrounds |
| Links & Buttons | `sky-blue` | #0ea5e9 | Interactive elements stand out |
| Admin/Warnings | `yellow-500` | #eab308 | System alerts & admin features |

---

## 🧭 Layout Patterns

### Left Sidebar (Elder Style)

Perfect for apps with lots of navigation. It's fixed, collapsible, and super clean.

```
┌─────────────────────────────────────────────────────────────┐
│ 🐧 Logo                                                     │
├─────────────────────────────────────────────────────────────┤
│ 📊 Dashboard                                                │
│ 🔍 Search                                                   │
│ 📋 Overview                                                 │
├─────────────────────────────────────────────────────────────┤
│ 📦 Assets                                          [▼]       │
│   ├── Entities                                              │
│   ├── Organizations                                         │
│   └── Services                                              │
├─────────────────────────────────────────────────────────────┤
│ ⚙️  Settings                                       [▶]       │
│    (collapsed - click to expand)                            │
├─────────────────────────────────────────────────────────────┤
│ 🔐 System Settings                          [⚠️ yellow]     │
├─────────────────────────────────────────────────────────────┤
│ 👤 Profile                                                  │
│ 🚪 Logout                                                   │
└─────────────────────────────────────────────────────────────┘
```

**Implementation Checklist:**

✅ Fixed positioning on left edge, full height
```jsx
<div className="fixed inset-y-0 left-0 w-64 bg-slate-800 border-r border-slate-700">
```

✅ Collapsible category groups with state management
```typescript
const [collapsedCategories, setCollapsedCategories] = useState<Record<string, boolean>>({})

const toggleCategory = (header: string) => {
  setCollapsedCategories(prev => ({
    ...prev,
    [header]: !prev[header]
  }))
}
```

✅ Active link highlighting with blue background
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

✅ Admin items get special yellow styling
```jsx
className={isActive
  ? 'bg-yellow-600/20 text-yellow-500 border border-yellow-600/30'
  : 'text-amber-400 hover:bg-slate-700 hover:text-amber-200'}
```

✅ Main content offset to match sidebar width
```jsx
<div className="pl-64">
  <main className="min-h-screen">
    <Outlet />
  </main>
</div>
```

✅ Use `lucide-react` icons, consistently sized at `w-5 h-5`

---

### Tab Navigation (WaddlePerf Style)

Organize content sections with horizontal tabs. Super clean, very intuitive.

```
┌────────────────────────────────────────────────────────────┐
│ 📊 Overview  📡 Network  🔍 Trace  💾 Download             │
│ ═════════════                                              │
│ (blue underline shows active tab)                          │
├────────────────────────────────────────────────────────────┤
│                                                            │
│            Tab Content Goes Here                          │
│            Smooth transitions between tabs                 │
│                                                            │
└────────────────────────────────────────────────────────────┘
```

**Tab Button Styling Magic:**

```css
.tab-button {
  padding: 0.75rem 1.5rem;
  background: transparent;
  border: none;
  border-bottom: 3px solid transparent;
  color: var(--text-secondary);  /* Gold by default */
  font-size: 1rem;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;  /* Smooth color transitions */
  margin-bottom: -2px;   /* Neat overlap trick */
}

.tab-button:hover {
  color: var(--text-light);  /* Lighter gold on hover */
}

.tab-button.active {
  color: var(--primary-500);       /* Blue when active */
  border-bottom-color: var(--primary-500);  /* Blue underline */
  font-weight: 600;  /* Slightly bolder */
}
```

**React Implementation:**

```typescript
type TabKey = 'overview' | 'details' | 'settings' | 'logs'
const [activeTab, setActiveTab] = useState<TabKey>('overview')

<div className="flex gap-4 border-b border-slate-700 mb-6">
  {tabs.map(tab => (
    <button
      key={tab.key}
      className={`pb-3 px-4 transition-all ${
        activeTab === tab.key
          ? 'border-b-2 border-primary-500 text-primary-500 font-semibold'
          : 'text-amber-400 hover:text-amber-200'
      }`}
      onClick={() => setActiveTab(tab.key)}
    >
      {tab.label}
    </button>
  ))}
</div>

{activeTab === 'overview' && <OverviewPanel />}
{activeTab === 'details' && <DetailsPanel />}
```

---

## 🧱 Component Library

### Card Component

Containers for content. Simple, elegant, reusable.

```jsx
export const Card = ({ title, children, className = '' }) => (
  <div className={`bg-slate-800 border border-slate-700 rounded-lg shadow-lg p-4 ${className}`}>
    {title && (
      <h3 className="text-sm font-semibold text-amber-400 mb-3">{title}</h3>
    )}
    <div className="text-amber-400">{children}</div>
  </div>
)
```

**Usage:**
```jsx
<Card title="Recent Activity">
  <p>Your activity feed goes here</p>
</Card>
```

### Button Component

Four flavors for every situation:

```jsx
const buttonVariants = {
  primary: 'bg-primary-600 hover:bg-primary-700 text-white',      // Main CTAs
  secondary: 'bg-slate-700 hover:bg-slate-600 text-amber-400',    // Alternative actions
  danger: 'bg-red-600 hover:bg-red-700 text-white',               // Delete/destructive
  ghost: 'bg-transparent hover:bg-slate-700 text-amber-400'       // Links in UI
}

export const Button = ({ variant = 'primary', size = 'md', children, ...props }) => (
  <button
    className={`rounded-lg font-medium transition-colors ${buttonVariants[variant]} ${sizeClasses[size]}`}
    {...props}
  >
    {children}
  </button>
)
```

**Usage:**
```jsx
<Button variant="primary">Save Changes</Button>
<Button variant="secondary">Cancel</Button>
<Button variant="danger">Delete</Button>
<Button variant="ghost">Learn More</Button>
```

---

## 📱 Responsive Design Tips

- **Mobile First**: Style for phones, then enhance with `lg:`, `xl:` breakpoints
- **Grid Magic**: Use Tailwind's grid for flexible layouts
- **Test Everything**: Check your work on actual devices, not just browser resizing
- **Touch Targets**: Buttons should be at least 44×44px (easy to tap)
- **Overflow**: Remember that mobile screens are narrow. Test long text, long names, long labels

Example responsive layout:
```jsx
<div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
  {items.map(item => <Card key={item.id}>{item.name}</Card>)}
</div>
```

---

## ♿ Making It Work for Everyone

Accessibility isn't optional. It's about being respectful to all users.

### Keyboard Navigation ⌨️
Every button, link, and form input must work with keyboard alone.
```jsx
<button
  onClick={handleClick}
  onKeyDown={(e) => e.key === 'Enter' && handleClick()}
>
  Action
</button>
```

### Focus States 👁️
Make focus obvious. Blue ring around focused elements:
```jsx
<input
  className="focus:ring-2 focus:ring-primary-500 focus:outline-none"
/>
```

### Semantic HTML 🏗️
Use proper HTML elements. Not everything is a `<div>`:
```jsx
<nav>Navigation goes here</nav>
<main>Main content here</main>
<article>Article content</article>
<button>Use button, not div with onClick</button>
```

### ARIA Labels 🗣️
Label things for screen readers:
```jsx
<button aria-label="Close menu">×</button>
<div aria-live="polite">Status updates</div>
```

### Color Contrast ⚫⚪
Text must have 4.5:1 contrast ratio minimum. Our gold on dark works great!

### Respect Motion Preferences 🎬
Some users get sick from animations:
```css
@media (prefers-reduced-motion: reduce) {
  * {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## 🚫 Common UI Mistakes (Don't Do These!)

| ❌ Mistake | ✅ Fix |
|-----------|--------|
| No focus indicators | Add `focus:ring-2 focus:ring-primary-500` |
| Text too small (<14px) | Use base text size minimum |
| Poor color contrast | Check with WebAIM contrast checker |
| Buttons that don't look clickable | Use color, shadows, hover states |
| No loading states | Show spinners for async actions |
| Hardcoded widths | Use Tailwind's responsive classes |
| Text that changes on hover | Annoys users, breaks mobile |
| Links that open in new tabs without warning | Tell users with icon or label |
| Keyboard traps | Make sure Tab key works everywhere |
| Forgetting the sidebar offset | `pl-64` for main content |

---

## 📦 Required Dependencies

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

---

## 🎨 Tailwind CSS v4 Theme Configuration

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

---

## ✨ Design Quick Checklist

- ✅ Dark backgrounds, gold text, blue accents
- ✅ 200ms transitions for smooth feel
- ✅ Consistent spacing (use Tailwind utilities)
- ✅ Keyboard navigation works everywhere
- ✅ Focus indicators are visible
- ✅ Responsive on mobile (test it!)
- ✅ Color contrast is accessible
- ✅ Icons from lucide-react at `w-5 h-5`
- ✅ Sidebar has proper offset (`pl-64`)
- ✅ Admin items get yellow highlight
- ✅ Active navigation has blue background

Now go build something beautiful! 🚀
