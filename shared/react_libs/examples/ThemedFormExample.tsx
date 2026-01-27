import React, { useState } from 'react';
import { FormModalBuilder, FormField, ColorConfig } from '../src/components';

/**
 * Example: Default Dark Mode Theme (Navy & Gold)
 * The component defaults to a dark navy background with gold accents
 */
export const DefaultDarkModeExample: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);

  const fields: FormField[] = [
    { name: 'username', type: 'text', label: 'Username', required: true },
    { name: 'email', type: 'email', label: 'Email Address', required: true },
    { name: 'password', type: 'password', label: 'Password', required: true },
    { name: 'role', type: 'select', label: 'Role', required: true, options: [
      { value: 'admin', label: 'Administrator' },
      { value: 'user', label: 'User' },
    ]},
    { name: 'notifications', type: 'checkbox', label: 'Enable Email Notifications', defaultValue: true },
  ];

  return (
    <div className="p-8">
      <h2 className="text-xl font-bold mb-4">Default Dark Mode (Navy & Gold)</h2>
      <p className="text-gray-600 mb-4">
        No color configuration needed - beautiful dark mode out of the box!
      </p>

      <button
        onClick={() => setIsOpen(true)}
        className="px-4 py-2 bg-amber-500 text-slate-900 rounded-md hover:bg-amber-600"
      >
        Open Dark Mode Form
      </button>

      <FormModalBuilder
        title="Create Account"
        fields={fields}
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        onSubmit={async (data) => console.log(data)}
        // No colors prop = default navy & gold dark mode
      />
    </div>
  );
};

/**
 * Example: Light Mode Theme
 * Custom light theme with blue accents
 */
export const LightModeExample: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);

  const lightTheme: ColorConfig = {
    // Background colors - Light mode
    modalBackground: 'bg-white',
    headerBackground: 'bg-white',
    footerBackground: 'bg-gray-50',
    overlayBackground: 'bg-gray-500 bg-opacity-75',

    // Text colors - Dark text on light background
    titleText: 'text-gray-900',
    labelText: 'text-gray-700',
    descriptionText: 'text-gray-500',
    errorText: 'text-red-600',
    buttonText: 'text-white',

    // Field colors
    fieldBackground: 'bg-white',
    fieldBorder: 'border-gray-300',
    fieldText: 'text-gray-900',
    fieldPlaceholder: 'placeholder-gray-400',

    // Focus/Ring colors - Blue accents
    focusRing: 'focus:ring-blue-500',
    focusBorder: 'focus:border-blue-500',

    // Button colors
    primaryButton: 'bg-blue-600',
    primaryButtonHover: 'hover:bg-blue-700',
    secondaryButton: 'bg-white',
    secondaryButtonHover: 'hover:bg-gray-50',
    secondaryButtonBorder: 'border-gray-300',

    // Tab colors
    activeTab: 'text-blue-600',
    activeTabBorder: 'border-blue-500',
    inactiveTab: 'text-gray-500',
    inactiveTabHover: 'hover:text-gray-700 hover:border-gray-300',
    tabBorder: 'border-gray-200',
    errorTabText: 'text-red-600',
    errorTabBorder: 'border-red-300',
  };

  const fields: FormField[] = [
    { name: 'name', type: 'text', label: 'Product Name', required: true },
    { name: 'price', type: 'number', label: 'Price', required: true, min: 0 },
    { name: 'description', type: 'textarea', label: 'Description', rows: 4 },
    { name: 'category', type: 'select', label: 'Category', options: [
      { value: 'electronics', label: 'Electronics' },
      { value: 'clothing', label: 'Clothing' },
    ]},
  ];

  return (
    <div className="p-8">
      <h2 className="text-xl font-bold mb-4">Light Mode Theme</h2>
      <p className="text-gray-600 mb-4">
        Traditional light theme with blue accents.
      </p>

      <button
        onClick={() => setIsOpen(true)}
        className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
      >
        Open Light Mode Form
      </button>

      <FormModalBuilder
        title="Add Product"
        fields={fields}
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        onSubmit={async (data) => console.log(data)}
        colors={lightTheme}
      />
    </div>
  );
};

/**
 * Example: Purple & Pink Theme
 * Custom vibrant color scheme
 */
export const PurplePinkExample: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);

  const purplePinkTheme: ColorConfig = {
    // Background colors - Deep purple
    modalBackground: 'bg-purple-900',
    headerBackground: 'bg-purple-900',
    footerBackground: 'bg-purple-950',
    overlayBackground: 'bg-black bg-opacity-50',

    // Text colors - Pink and white
    titleText: 'text-pink-400',
    labelText: 'text-pink-300',
    descriptionText: 'text-purple-400',
    errorText: 'text-red-400',
    buttonText: 'text-white',

    // Field colors
    fieldBackground: 'bg-white',
    fieldBorder: 'border-purple-600',
    fieldText: 'text-purple-900',
    fieldPlaceholder: 'placeholder-purple-400',

    // Focus/Ring colors - Pink accents
    focusRing: 'focus:ring-pink-500',
    focusBorder: 'focus:border-pink-500',

    // Button colors
    primaryButton: 'bg-pink-500',
    primaryButtonHover: 'hover:bg-pink-600',
    secondaryButton: 'bg-purple-800',
    secondaryButtonHover: 'hover:bg-purple-700',
    secondaryButtonBorder: 'border-purple-600',

    // Tab colors
    activeTab: 'text-pink-400',
    activeTabBorder: 'border-pink-500',
    inactiveTab: 'text-purple-400',
    inactiveTabHover: 'hover:text-purple-300 hover:border-purple-500',
    tabBorder: 'border-purple-700',
    errorTabText: 'text-red-400',
    errorTabBorder: 'border-red-500',
  };

  const fields: FormField[] = [
    { name: 'title', type: 'text', label: 'Event Title', required: true },
    { name: 'date', type: 'date', label: 'Event Date', required: true },
    { name: 'time', type: 'time', label: 'Start Time', required: true },
    { name: 'location', type: 'text', label: 'Location' },
    { name: 'description', type: 'textarea', label: 'Description', rows: 3 },
  ];

  return (
    <div className="p-8">
      <h2 className="text-xl font-bold mb-4">Purple & Pink Theme</h2>
      <p className="text-gray-600 mb-4">
        Vibrant purple background with pink accents.
      </p>

      <button
        onClick={() => setIsOpen(true)}
        className="px-4 py-2 bg-pink-500 text-white rounded-md hover:bg-pink-600"
      >
        Open Purple/Pink Form
      </button>

      <FormModalBuilder
        title="Create Event"
        fields={fields}
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        onSubmit={async (data) => console.log(data)}
        colors={purplePinkTheme}
        width="lg"
      />
    </div>
  );
};

/**
 * Example: Emerald Green Theme
 * Professional green theme for financial/business apps
 */
export const EmeraldGreenExample: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);

  const emeraldTheme: ColorConfig = {
    // Background colors - Dark emerald
    modalBackground: 'bg-emerald-950',
    headerBackground: 'bg-emerald-950',
    footerBackground: 'bg-emerald-900',
    overlayBackground: 'bg-gray-900 bg-opacity-75',

    // Text colors - Light emerald and white
    titleText: 'text-emerald-400',
    labelText: 'text-emerald-300',
    descriptionText: 'text-emerald-200',
    errorText: 'text-red-400',
    buttonText: 'text-emerald-950',

    // Field colors
    fieldBackground: 'bg-white',
    fieldBorder: 'border-emerald-600',
    fieldText: 'text-emerald-900',
    fieldPlaceholder: 'placeholder-emerald-500',

    // Focus/Ring colors
    focusRing: 'focus:ring-emerald-500',
    focusBorder: 'focus:border-emerald-500',

    // Button colors
    primaryButton: 'bg-emerald-500',
    primaryButtonHover: 'hover:bg-emerald-600',
    secondaryButton: 'bg-emerald-800',
    secondaryButtonHover: 'hover:bg-emerald-700',
    secondaryButtonBorder: 'border-emerald-600',

    // Tab colors
    activeTab: 'text-emerald-400',
    activeTabBorder: 'border-emerald-500',
    inactiveTab: 'text-emerald-300',
    inactiveTabHover: 'hover:text-emerald-200 hover:border-emerald-500',
    tabBorder: 'border-emerald-700',
    errorTabText: 'text-red-400',
    errorTabBorder: 'border-red-500',
  };

  const fields: FormField[] = [
    { name: 'accountName', type: 'text', label: 'Account Name', required: true },
    { name: 'accountType', type: 'select', label: 'Account Type', required: true, options: [
      { value: 'checking', label: 'Checking' },
      { value: 'savings', label: 'Savings' },
      { value: 'investment', label: 'Investment' },
    ]},
    { name: 'initialDeposit', type: 'number', label: 'Initial Deposit ($)', required: true, min: 0 },
    { name: 'paperlessStatements', type: 'checkbox', label: 'Enroll in Paperless Statements', defaultValue: true },
  ];

  return (
    <div className="p-8">
      <h2 className="text-xl font-bold mb-4">Emerald Green Theme</h2>
      <p className="text-gray-600 mb-4">
        Professional dark theme with emerald accents for financial apps.
      </p>

      <button
        onClick={() => setIsOpen(true)}
        className="px-4 py-2 bg-emerald-500 text-emerald-950 rounded-md hover:bg-emerald-600"
      >
        Open Emerald Form
      </button>

      <FormModalBuilder
        title="Open New Account"
        fields={fields}
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        onSubmit={async (data) => console.log(data)}
        colors={emeraldTheme}
      />
    </div>
  );
};
