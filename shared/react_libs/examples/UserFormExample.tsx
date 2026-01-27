import React, { useState } from 'react';
import { FormModalBuilder, FormField } from '../src/components';

/**
 * Example: User Creation Form
 * Demonstrates common form patterns with the FormModalBuilder
 */
export const UserFormExample: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);

  const userFields: FormField[] = [
    {
      name: 'username',
      type: 'text',
      label: 'Username',
      description: 'Choose a unique username (3-20 characters)',
      required: true,
      placeholder: 'johndoe',
      validation: (value) => {
        if (value.length < 3) return 'Username must be at least 3 characters';
        if (value.length > 20) return 'Username must be at most 20 characters';
        if (!/^[a-zA-Z0-9_]+$/.test(value)) return 'Username can only contain letters, numbers, and underscores';
        return null;
      },
    },
    {
      name: 'email',
      type: 'email',
      label: 'Email Address',
      description: 'We will send a confirmation email',
      required: true,
      placeholder: 'john@example.com',
    },
    {
      name: 'password',
      type: 'password',
      label: 'Password',
      description: 'At least 8 characters with uppercase, lowercase, and number',
      required: true,
      validation: (value) => {
        if (value.length < 8) return 'Password must be at least 8 characters';
        if (!/[A-Z]/.test(value)) return 'Password must contain an uppercase letter';
        if (!/[a-z]/.test(value)) return 'Password must contain a lowercase letter';
        if (!/[0-9]/.test(value)) return 'Password must contain a number';
        return null;
      },
    },
    {
      name: 'role',
      type: 'select',
      label: 'User Role',
      description: 'Determines access permissions',
      required: true,
      options: [
        { value: 'admin', label: 'Administrator - Full Access' },
        { value: 'maintainer', label: 'Maintainer - Read/Write' },
        { value: 'viewer', label: 'Viewer - Read Only' },
      ],
      defaultValue: 'viewer',
    },
    {
      name: 'department',
      type: 'select',
      label: 'Department',
      options: [
        { value: 'engineering', label: 'Engineering' },
        { value: 'sales', label: 'Sales' },
        { value: 'support', label: 'Support' },
        { value: 'marketing', label: 'Marketing' },
      ],
    },
    {
      name: 'bio',
      type: 'textarea',
      label: 'Bio',
      description: 'Tell us a bit about yourself (optional)',
      rows: 4,
      placeholder: 'I am a software developer with...',
    },
    {
      name: 'notifications',
      type: 'checkbox',
      label: 'Send me email notifications',
      defaultValue: true,
    },
    {
      name: 'newsletter',
      type: 'checkbox',
      label: 'Subscribe to newsletter',
      defaultValue: false,
    },
  ];

  const handleSubmit = async (data: Record<string, any>) => {
    console.log('Creating user:', data);

    // Simulate API call
    await new Promise((resolve) => setTimeout(resolve, 1000));

    // In real app:
    // const response = await fetch('/api/v1/users', {
    //   method: 'POST',
    //   headers: { 'Content-Type': 'application/json' },
    //   body: JSON.stringify(data),
    // });
    // if (!response.ok) throw new Error('Failed to create user');

    alert(`User ${data.username} created successfully!`);
  };

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-4">Form Modal Builder Example</h1>
      <button
        onClick={() => setIsOpen(true)}
        className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700"
      >
        Create New User
      </button>

      <FormModalBuilder
        title="Create New User Account"
        fields={userFields}
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        onSubmit={handleSubmit}
        submitButtonText="Create User"
        cancelButtonText="Cancel"
        width="lg"
        maxHeight="max-h-[85vh]"
      />
    </div>
  );
};

/**
 * Example: Product Form with File Upload
 */
export const ProductFormExample: React.FC = () => {
  const [isOpen, setIsOpen] = useState(false);

  const productFields: FormField[] = [
    {
      name: 'name',
      type: 'text',
      label: 'Product Name',
      required: true,
      placeholder: 'Awesome Widget',
    },
    {
      name: 'sku',
      type: 'text',
      label: 'SKU',
      description: 'Stock Keeping Unit',
      required: true,
      placeholder: 'WIDGET-001',
    },
    {
      name: 'price',
      type: 'number',
      label: 'Price (USD)',
      required: true,
      min: 0,
      defaultValue: 0,
    },
    {
      name: 'stock',
      type: 'number',
      label: 'Stock Quantity',
      required: true,
      min: 0,
      defaultValue: 0,
    },
    {
      name: 'category',
      type: 'radio',
      label: 'Category',
      required: true,
      options: [
        { value: 'electronics', label: 'Electronics' },
        { value: 'clothing', label: 'Clothing' },
        { value: 'books', label: 'Books' },
        { value: 'toys', label: 'Toys' },
      ],
    },
    {
      name: 'description',
      type: 'textarea',
      label: 'Description',
      required: true,
      rows: 5,
    },
    {
      name: 'image',
      type: 'file',
      label: 'Product Image',
      accept: 'image/*',
    },
    {
      name: 'featured',
      type: 'checkbox',
      label: 'Feature this product on homepage',
      defaultValue: false,
    },
  ];

  const handleSubmit = async (data: Record<string, any>) => {
    console.log('Creating product:', data);
    await new Promise((resolve) => setTimeout(resolve, 1000));
    alert(`Product "${data.name}" created!`);
  };

  return (
    <div className="p-8">
      <button
        onClick={() => setIsOpen(true)}
        className="px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700"
      >
        Add New Product
      </button>

      <FormModalBuilder
        title="Add New Product"
        fields={productFields}
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        onSubmit={handleSubmit}
        submitButtonText="Add Product"
        width="xl"
        backgroundColor="bg-gray-50"
      />
    </div>
  );
};
