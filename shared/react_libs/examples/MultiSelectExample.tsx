import React, { useState } from 'react';
import { FormModalBuilder, FormField } from '../src/components/FormModalBuilder';

/**
 * Example showing multi-select checkbox usage in FormModalBuilder
 *
 * This demonstrates:
 * - checkbox_multi field type for multi-select checkboxes
 * - radio field type for single selection
 * - Conditional visibility with showWhen
 * - Required multi-select validation
 */
export default function MultiSelectExample() {
  const [isOpen, setIsOpen] = useState(false);
  const [result, setResult] = useState<Record<string, any> | null>(null);

  const fields: FormField[] = [
    {
      name: 'title',
      type: 'text',
      label: 'Issue Title',
      required: true,
      placeholder: 'Enter issue title',
    },
    {
      name: 'priority',
      type: 'radio',
      label: 'Priority',
      required: true,
      options: [
        { value: 'low', label: 'Low' },
        { value: 'medium', label: 'Medium' },
        { value: 'high', label: 'High' },
        { value: 'critical', label: 'Critical' },
      ],
      defaultValue: 'medium',
    },
    {
      name: 'assignment_type',
      type: 'radio',
      label: 'Assign To',
      required: true,
      options: [
        { value: 'organization', label: 'Organization' },
        { value: 'entity', label: 'Entity' },
      ],
      defaultValue: 'organization',
    },
    {
      name: 'organization_id',
      type: 'select',
      label: 'Organization',
      options: [
        { value: 1, label: 'Engineering' },
        { value: 2, label: 'Operations' },
        { value: 3, label: 'Security' },
      ],
      showWhen: (values) => values.assignment_type === 'organization',
    },
    {
      name: 'entity_ids',
      type: 'checkbox_multi',
      label: 'Entities',
      helpText: 'Select one or more entities to assign this issue',
      options: [
        { value: 1, label: 'api-server-1' },
        { value: 2, label: 'api-server-2' },
        { value: 3, label: 'database-primary' },
        { value: 4, label: 'database-replica' },
        { value: 5, label: 'redis-cache' },
      ],
      showWhen: (values) => values.assignment_type === 'entity',
    },
    {
      name: 'labels',
      type: 'checkbox_multi',
      label: 'Labels',
      helpText: 'Optionally select labels to categorize this issue',
      options: [
        { value: 'bug', label: 'Bug' },
        { value: 'feature', label: 'Feature Request' },
        { value: 'enhancement', label: 'Enhancement' },
        { value: 'documentation', label: 'Documentation' },
        { value: 'security', label: 'Security' },
      ],
    },
  ];

  const handleSubmit = (data: Record<string, any>) => {
    console.log('Form submitted:', data);
    setResult(data);
    setIsOpen(false);
  };

  return (
    <div className="p-8">
      <h1 className="text-2xl font-bold mb-4">Multi-Select Checkbox Example</h1>

      <button
        onClick={() => setIsOpen(true)}
        className="px-4 py-2 bg-amber-500 text-white rounded-lg hover:bg-amber-600"
      >
        Open Form
      </button>

      {result && (
        <div className="mt-6 p-4 bg-slate-800 rounded-lg">
          <h2 className="text-lg font-semibold mb-2 text-amber-400">Form Result:</h2>
          <pre className="text-sm text-slate-300 whitespace-pre-wrap">
            {JSON.stringify(result, null, 2)}
          </pre>
        </div>
      )}

      <FormModalBuilder
        title="Create Issue with Multi-Select"
        fields={fields}
        isOpen={isOpen}
        onClose={() => setIsOpen(false)}
        onSubmit={handleSubmit}
        submitButtonText="Create Issue"
      />
    </div>
  );
}
