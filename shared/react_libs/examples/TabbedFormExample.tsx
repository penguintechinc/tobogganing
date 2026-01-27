import React, { useState } from 'react';
import { FormModalBuilder, FormField, FormTab } from '../src/components';

/**
 * Example: Automatic Tab Generation
 * With 12+ fields, tabs are automatically created
 */
export const AutoTabbedFormExample: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);

  // 12 fields - will automatically create tabs (threshold: 8, fieldsPerTab: 6)
  const fields: FormField[] = [
    // First 6 fields -> "General" tab
    { name: 'firstName', type: 'text', label: 'First Name', required: true },
    { name: 'lastName', type: 'text', label: 'Last Name', required: true },
    { name: 'email', type: 'email', label: 'Email', required: true },
    { name: 'phone', type: 'tel', label: 'Phone Number' },
    { name: 'birthdate', type: 'date', label: 'Birth Date' },
    { name: 'gender', type: 'select', label: 'Gender', options: [
      { value: 'male', label: 'Male' },
      { value: 'female', label: 'Female' },
      { value: 'other', label: 'Other' },
    ]},

    // Next 6 fields -> "Step 2" tab
    { name: 'address', type: 'text', label: 'Street Address', required: true },
    { name: 'city', type: 'text', label: 'City', required: true },
    { name: 'state', type: 'text', label: 'State/Province' },
    { name: 'zipCode', type: 'text', label: 'ZIP/Postal Code' },
    { name: 'country', type: 'text', label: 'Country', defaultValue: 'USA' },
    { name: 'bio', type: 'textarea', label: 'Biography', rows: 4 },
  ];

  const handleSubmit = async (data: Record<string, any>) => {
    console.log('Form submitted:', data);
    await new Promise((resolve) => setTimeout(resolve, 1000));
    alert('User registered successfully!');
  };

  return (
    <div className="p-8">
      <h2 className="text-xl font-bold mb-4">Auto-Tabbed Form (12 fields)</h2>
      <p className="text-gray-600 mb-4">
        This form has 12 fields. Since the default threshold is 8 fields, tabs will be automatically created
        with 6 fields per tab.
      </p>

      <button
        onClick={() => setIsOpen(true)}
        className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
      >
        Open Auto-Tabbed Form
      </button>

      <FormModalBuilder
        title="User Registration (Auto-Tabbed)"
        fields={fields}
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        onSubmit={handleSubmit}
        width="lg"
      />
    </div>
  );
};

/**
 * Example: Manual Tab Assignment via field.tab
 * Organize fields by category using the tab property
 */
export const ManualTabAssignmentExample: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);

  const fields: FormField[] = [
    // Personal Information tab
    { name: 'firstName', type: 'text', label: 'First Name', required: true, tab: 'Personal Info' },
    { name: 'lastName', type: 'text', label: 'Last Name', required: true, tab: 'Personal Info' },
    { name: 'email', type: 'email', label: 'Email', required: true, tab: 'Personal Info' },
    { name: 'phone', type: 'tel', label: 'Phone Number', tab: 'Personal Info' },

    // Account Settings tab
    { name: 'username', type: 'text', label: 'Username', required: true, tab: 'Account' },
    { name: 'password', type: 'password', label: 'Password', required: true, tab: 'Account' },
    { name: 'role', type: 'select', label: 'Role', required: true, tab: 'Account', options: [
      { value: 'admin', label: 'Administrator' },
      { value: 'user', label: 'User' },
    ]},

    // Preferences tab
    { name: 'timezone', type: 'select', label: 'Timezone', tab: 'Preferences', options: [
      { value: 'utc', label: 'UTC' },
      { value: 'est', label: 'Eastern' },
      { value: 'pst', label: 'Pacific' },
    ]},
    { name: 'notifications', type: 'checkbox', label: 'Email Notifications', tab: 'Preferences', defaultValue: true },
    { name: 'newsletter', type: 'checkbox', label: 'Subscribe to Newsletter', tab: 'Preferences' },
  ];

  const handleSubmit = async (data: Record<string, any>) => {
    console.log('Form submitted:', data);
    await new Promise((resolve) => setTimeout(resolve, 1000));
    alert('Account created!');
  };

  return (
    <div className="p-8">
      <h2 className="text-xl font-bold mb-4">Manual Tab Assignment</h2>
      <p className="text-gray-600 mb-4">
        Fields are organized into tabs using the <code className="bg-gray-100 px-1 rounded">tab</code> property.
      </p>

      <button
        onClick={() => setIsOpen(true)}
        className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700"
      >
        Open Tab-Assigned Form
      </button>

      <FormModalBuilder
        title="Create Account"
        fields={fields}
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        onSubmit={handleSubmit}
        width="lg"
      />
    </div>
  );
};

/**
 * Example: Explicit Tab Configuration
 * Define tabs manually with complete control
 */
export const ExplicitTabsExample: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);

  const tabs: FormTab[] = [
    {
      id: 'basic',
      label: 'Basic Info',
      fields: [
        { name: 'productName', type: 'text', label: 'Product Name', required: true },
        { name: 'sku', type: 'text', label: 'SKU', required: true },
        { name: 'price', type: 'number', label: 'Price', required: true, min: 0 },
        { name: 'category', type: 'select', label: 'Category', required: true, options: [
          { value: 'electronics', label: 'Electronics' },
          { value: 'clothing', label: 'Clothing' },
          { value: 'books', label: 'Books' },
        ]},
      ],
    },
    {
      id: 'details',
      label: 'Details',
      fields: [
        { name: 'description', type: 'textarea', label: 'Description', required: true, rows: 4 },
        { name: 'features', type: 'textarea', label: 'Features', rows: 3 },
        { name: 'weight', type: 'number', label: 'Weight (kg)', min: 0 },
        { name: 'dimensions', type: 'text', label: 'Dimensions (L×W×H)' },
      ],
    },
    {
      id: 'inventory',
      label: 'Inventory',
      fields: [
        { name: 'stock', type: 'number', label: 'Stock Quantity', required: true, min: 0, defaultValue: 0 },
        { name: 'reorderLevel', type: 'number', label: 'Reorder Level', min: 0 },
        { name: 'supplier', type: 'text', label: 'Supplier' },
        { name: 'trackInventory', type: 'checkbox', label: 'Track Inventory', defaultValue: true },
      ],
    },
    {
      id: 'media',
      label: 'Media',
      fields: [
        { name: 'image', type: 'file', label: 'Product Image', accept: 'image/*' },
        { name: 'imageUrl', type: 'url', label: 'Or Image URL' },
        { name: 'videoUrl', type: 'url', label: 'Video URL (optional)' },
        { name: 'featured', type: 'checkbox', label: 'Feature on Homepage' },
      ],
    },
  ];

  // Flatten all fields from tabs for form data initialization
  const allFields = tabs.flatMap((tab) => tab.fields);

  const handleSubmit = async (data: Record<string, any>) => {
    console.log('Product created:', data);
    await new Promise((resolve) => setTimeout(resolve, 1000));
    alert(`Product "${data.productName}" created successfully!`);
  };

  return (
    <div className="p-8">
      <h2 className="text-xl font-bold mb-4">Explicit Tab Configuration</h2>
      <p className="text-gray-600 mb-4">
        Tabs are explicitly defined with the <code className="bg-gray-100 px-1 rounded">tabs</code> prop for complete control.
      </p>

      <button
        onClick={() => setIsOpen(true)}
        className="px-4 py-2 bg-purple-600 text-white rounded-md hover:bg-purple-700"
      >
        Create Product
      </button>

      <FormModalBuilder
        title="Add New Product"
        fields={allFields}
        tabs={tabs}
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        onSubmit={handleSubmit}
        width="xl"
      />
    </div>
  );
};

/**
 * Example: Custom Tab Threshold
 * Control when tabs are automatically created
 */
export const CustomThresholdExample: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);

  const fields: FormField[] = Array.from({ length: 10 }, (_, i) => ({
    name: `field${i + 1}`,
    type: 'text' as const,
    label: `Field ${i + 1}`,
    required: i < 3,
  }));

  return (
    <div className="p-8">
      <h2 className="text-xl font-bold mb-4">Custom Threshold (10 fields, threshold: 5, per tab: 4)</h2>

      <button
        onClick={() => setIsOpen(true)}
        className="px-4 py-2 bg-orange-600 text-white rounded-md hover:bg-orange-700"
      >
        Open Custom Threshold Form
      </button>

      <FormModalBuilder
        title="Custom Threshold Example"
        fields={fields}
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        onSubmit={async (data) => console.log(data)}
        autoTabThreshold={5}  // Create tabs if more than 5 fields
        fieldsPerTab={4}      // Put 4 fields per tab
        width="md"
      />
    </div>
  );
};
