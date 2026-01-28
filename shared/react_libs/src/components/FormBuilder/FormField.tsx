/**
 * FormField Component
 *
 * Dynamic form field renderer that supports multiple input types.
 * Handles validation errors, helper text, and field-specific configuration.
 */

import React from 'react';
import { FormFieldProps } from './types';

export const FormField: React.FC<FormFieldProps> = ({
  field,
  value,
  error,
  onChange,
  onBlur,
}) => {
  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement | HTMLSelectElement>) => {
    const newValue = field.type === 'checkbox'
      ? (e.target as HTMLInputElement).checked
      : field.type === 'number'
      ? e.target.value === '' ? '' : Number(e.target.value)
      : e.target.value;

    onChange(field.name, newValue);

    if (field.onChange) {
      field.onChange(newValue);
    }
  };

  const handleBlur = () => {
    if (onBlur) {
      onBlur(field.name);
    }
  };

  const renderInput = () => {
    const commonProps = {
      id: field.name,
      name: field.name,
      value: field.type === 'checkbox' ? undefined : (value ?? ''),
      checked: field.type === 'checkbox' ? Boolean(value) : undefined,
      onChange: handleChange,
      onBlur: handleBlur,
      required: field.required,
      disabled: field.disabled,
      autoFocus: field.autoFocus,
      placeholder: field.placeholder,
      min: field.min,
      max: field.max,
      minLength: field.minLength,
      maxLength: field.maxLength,
      pattern: field.pattern,
      step: field.step,
      className: field.type === 'checkbox'
        ? 'h-4 w-4 text-gold-400 focus:ring-gold-400 border-gray-600 rounded bg-dark-800'
        : 'input',
    };

    switch (field.type) {
      case 'textarea':
        return (
          <textarea
            {...commonProps}
            rows={field.rows || 3}
            className="input"
          />
        );

      case 'select':
        return (
          <select {...commonProps} className="input">
            <option value="">Select...</option>
            {field.options?.map((option) => (
              <option
                key={option.value}
                value={option.value}
                disabled={option.disabled}
              >
                {option.label}
              </option>
            ))}
          </select>
        );

      case 'radio':
        return (
          <div className="space-y-2">
            {field.options?.map((option) => (
              <label
                key={option.value}
                className="flex items-center space-x-2 cursor-pointer"
              >
                <input
                  type="radio"
                  name={field.name}
                  value={option.value}
                  checked={value === option.value}
                  onChange={handleChange}
                  onBlur={handleBlur}
                  disabled={option.disabled || field.disabled}
                  required={field.required}
                  className="h-4 w-4 text-gold-400 focus:ring-gold-400 border-gray-600 bg-dark-800"
                />
                <span className="text-gray-300">{option.label}</span>
              </label>
            ))}
          </div>
        );

      case 'checkbox':
        return (
          <label className="flex items-center space-x-2 cursor-pointer">
            <input type="checkbox" {...commonProps} />
            <span className="text-gray-300">{field.label}</span>
          </label>
        );

      default:
        return <input type={field.type} {...commonProps} />;
    }
  };

  if (field.type === 'checkbox') {
    return (
      <div className={field.className}>
        {renderInput()}
        {field.helperText && (
          <p className="mt-1 text-sm text-gray-400">{field.helperText}</p>
        )}
        {error && (
          <p className="mt-1 text-sm text-red-500">{error}</p>
        )}
      </div>
    );
  }

  return (
    <div className={field.className}>
      <label htmlFor={field.name} className="block text-sm font-medium text-gray-300 mb-1">
        {field.label}
        {field.required && <span className="text-red-500 ml-1">*</span>}
      </label>
      {renderInput()}
      {field.helperText && !error && (
        <p className="mt-1 text-sm text-gray-400">{field.helperText}</p>
      )}
      {error && (
        <p className="mt-1 text-sm text-red-500">{error}</p>
      )}
    </div>
  );
};
