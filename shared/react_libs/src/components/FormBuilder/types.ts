/**
 * FormBuilder Types
 *
 * Type definitions for the flexible FormBuilder component that supports
 * both modal and inline rendering modes.
 */

import { ReactNode } from 'react';

export type FieldType =
  | 'text'
  | 'email'
  | 'password'
  | 'number'
  | 'textarea'
  | 'select'
  | 'checkbox'
  | 'radio'
  | 'date'
  | 'time'
  | 'datetime-local'
  | 'tel'
  | 'url';

export interface SelectOption {
  value: string | number;
  label: string;
  disabled?: boolean;
}

export interface FieldConfig {
  name: string;
  label: string;
  type: FieldType;
  placeholder?: string;
  required?: boolean;
  disabled?: boolean;
  autoFocus?: boolean;
  defaultValue?: any;
  min?: number | string;
  max?: number | string;
  minLength?: number;
  maxLength?: number;
  pattern?: string;
  step?: number | string;
  rows?: number; // For textarea
  options?: SelectOption[]; // For select, radio
  helperText?: string;
  validate?: (value: any) => string | null;
  onChange?: (value: any) => void;
  className?: string;
}

export interface FormConfig {
  fields: FieldConfig[];
  title?: string;
  submitLabel?: string;
  cancelLabel?: string;
  onSubmit: (data: Record<string, any>) => void | Promise<void>;
  onCancel?: () => void;
  initialData?: Record<string, any>;
  validateOnChange?: boolean;
  validateOnBlur?: boolean;
  className?: string;
}

export interface FormBuilderProps extends FormConfig {
  mode?: 'inline' | 'modal';
  isOpen?: boolean;
  loading?: boolean;
  error?: string | null;
  closeOnOverlayClick?: boolean;
  showCloseButton?: boolean;
}

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  title?: string;
  children: ReactNode;
  className?: string;
  closeOnOverlayClick?: boolean;
  showCloseButton?: boolean;
}

export interface FormFieldProps {
  field: FieldConfig;
  value: any;
  error?: string;
  onChange: (name: string, value: any) => void;
  onBlur?: (name: string) => void;
}
