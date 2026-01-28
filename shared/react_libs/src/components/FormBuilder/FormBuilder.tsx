/**
 * FormBuilder Component
 *
 * Flexible form builder that supports both modal and inline rendering modes.
 * - mode='modal': Renders form inside a modal dialog
 * - mode='inline': Renders form directly in the page
 *
 * Features:
 * - Dynamic field configuration
 * - Built-in validation
 * - Error handling
 * - Loading states
 * - Customizable styling
 */

import React from 'react';
import { FormBuilderProps } from './types';
import { Modal } from './Modal';
import { FormField } from './FormField';
import { useFormBuilder } from '../../hooks/useFormBuilder';

export const FormBuilder: React.FC<FormBuilderProps> = ({
  mode = 'inline',
  isOpen = true,
  fields,
  title,
  submitLabel = 'Submit',
  cancelLabel = 'Cancel',
  onSubmit,
  onCancel,
  initialData,
  validateOnChange = false,
  validateOnBlur = true,
  loading = false,
  error = null,
  closeOnOverlayClick = true,
  showCloseButton = true,
  className = '',
}) => {
  const {
    values,
    errors,
    touched,
    isSubmitting,
    handleChange,
    handleBlur,
    handleSubmit,
  } = useFormBuilder({
    fields,
    initialData,
    onSubmit,
    validateOnChange,
    validateOnBlur,
  });

  const renderForm = () => (
    <form onSubmit={handleSubmit} className={`space-y-4 ${className}`}>
      {error && (
        <div className="p-3 bg-red-900/20 border border-red-500 rounded text-red-400 text-sm">
          {error}
        </div>
      )}

      {fields.map((field) => (
        <FormField
          key={field.name}
          field={field}
          value={values[field.name]}
          error={touched[field.name] ? errors[field.name] : undefined}
          onChange={handleChange}
          onBlur={handleBlur}
        />
      ))}

      <div className="flex justify-end gap-3 pt-2">
        {onCancel && (
          <button
            type="button"
            onClick={onCancel}
            disabled={isSubmitting || loading}
            className="btn-secondary"
          >
            {cancelLabel}
          </button>
        )}
        <button
          type="submit"
          disabled={isSubmitting || loading}
          className="btn-primary"
        >
          {isSubmitting || loading ? (
            <span className="flex items-center gap-2">
              <svg
                className="animate-spin h-4 w-4"
                xmlns="http://www.w3.org/2000/svg"
                fill="none"
                viewBox="0 0 24 24"
              >
                <circle
                  className="opacity-25"
                  cx="12"
                  cy="12"
                  r="10"
                  stroke="currentColor"
                  strokeWidth="4"
                />
                <path
                  className="opacity-75"
                  fill="currentColor"
                  d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                />
              </svg>
              {submitLabel}...
            </span>
          ) : (
            submitLabel
          )}
        </button>
      </div>
    </form>
  );

  if (mode === 'modal') {
    return (
      <Modal
        isOpen={isOpen}
        onClose={onCancel || (() => {})}
        title={title}
        closeOnOverlayClick={closeOnOverlayClick}
        showCloseButton={showCloseButton}
      >
        {renderForm()}
      </Modal>
    );
  }

  return (
    <div className={className}>
      {title && <h2 className="text-xl font-bold text-gold-400 mb-4">{title}</h2>}
      {renderForm()}
    </div>
  );
};
