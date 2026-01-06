/**
 * String validators for input validation.
 */

import { type ValidationResult, type Validator, success, failure } from './index.js';

export interface NotEmptyOptions {
  errorMessage?: string;
}

/**
 * Validates that a string is not empty or whitespace-only.
 * Returns the trimmed string.
 */
export function notEmpty(options: NotEmptyOptions = {}): Validator<string, string> {
  const errorMessage = options.errorMessage ?? 'Value cannot be empty';

  return (value: string): ValidationResult<string> => {
    if (typeof value !== 'string') {
      return failure('Value must be a string');
    }

    const trimmed = value.trim();
    if (trimmed === '') {
      return failure(errorMessage);
    }

    return success(trimmed);
  };
}

export interface LengthOptions {
  errorMessage?: string;
}

/**
 * Validates that a string length is within a range.
 * @param minLen - Minimum length (inclusive)
 * @param maxLen - Maximum length (inclusive), 0 for unlimited
 */
export function length(minLen: number, maxLen: number = 0, options: LengthOptions = {}): Validator<string, string> {
  return (value: string): ValidationResult<string> => {
    if (typeof value !== 'string') {
      return failure('Value must be a string');
    }

    const len = value.length;

    if (len < minLen) {
      return failure(options.errorMessage ?? `Value must be at least ${minLen} characters`);
    }

    if (maxLen > 0 && len > maxLen) {
      return failure(options.errorMessage ?? `Value must be at most ${maxLen} characters`);
    }

    return success(value);
  };
}

/**
 * Validates minimum string length.
 */
export function minLength(min: number, options: LengthOptions = {}): Validator<string, string> {
  return length(min, 0, options);
}

/**
 * Validates maximum string length.
 */
export function maxLength(max: number, options: LengthOptions = {}): Validator<string, string> {
  return length(0, max, options);
}

export interface MatchOptions {
  errorMessage?: string;
}

/**
 * Validates that a string matches a regex pattern.
 */
export function match(pattern: RegExp | string, options: MatchOptions = {}): Validator<string, string> {
  const regex = typeof pattern === 'string' ? new RegExp(pattern) : pattern;
  const errorMessage = options.errorMessage ?? 'Value does not match required pattern';

  return (value: string): ValidationResult<string> => {
    if (typeof value !== 'string') {
      return failure('Value must be a string');
    }

    if (!regex.test(value)) {
      return failure(errorMessage);
    }

    return success(value);
  };
}

export interface AlphanumericOptions {
  allowUnderscore?: boolean;
  allowDash?: boolean;
  errorMessage?: string;
}

/**
 * Validates that a string contains only alphanumeric characters.
 */
export function alphanumeric(options: AlphanumericOptions = {}): Validator<string, string> {
  const { allowUnderscore = false, allowDash = false } = options;
  const errorMessage = options.errorMessage ?? 'Value must contain only alphanumeric characters';

  let chars = 'a-zA-Z0-9';
  if (allowUnderscore) chars += '_';
  if (allowDash) chars += '-';

  const regex = new RegExp(`^[${chars}]+$`);

  return (value: string): ValidationResult<string> => {
    if (typeof value !== 'string') {
      return failure('Value must be a string');
    }

    if (value === '') {
      return failure('Value cannot be empty');
    }

    if (!regex.test(value)) {
      return failure(errorMessage);
    }

    return success(value);
  };
}

export interface SlugOptions {
  errorMessage?: string;
}

/**
 * Validates that a string is a valid URL slug.
 * A valid slug contains only lowercase letters, numbers, and hyphens.
 */
export function slug(options: SlugOptions = {}): Validator<string, string> {
  const errorMessage = options.errorMessage ?? 'Value must be a valid URL slug';
  const slugRegex = /^[a-z0-9]+(?:-[a-z0-9]+)*$/;

  return (value: string): ValidationResult<string> => {
    if (typeof value !== 'string') {
      return failure('Value must be a string');
    }

    if (value === '') {
      return failure('Value cannot be empty');
    }

    if (!slugRegex.test(value)) {
      return failure(errorMessage);
    }

    return success(value);
  };
}

export interface IsInOptions {
  caseSensitive?: boolean;
  errorMessage?: string;
}

/**
 * Validates that a value is in an allowed set.
 */
export function isIn(allowedOptions: readonly string[], options: IsInOptions = {}): Validator<string, string> {
  const { caseSensitive = true } = options;

  const optionSet = new Set(
    caseSensitive ? allowedOptions : allowedOptions.map(o => o.toLowerCase())
  );

  return (value: string): ValidationResult<string> => {
    if (typeof value !== 'string') {
      return failure('Value must be a string');
    }

    const checkValue = caseSensitive ? value : value.toLowerCase();

    if (!optionSet.has(checkValue)) {
      return failure(options.errorMessage ?? `Value must be one of: ${allowedOptions.join(', ')}`);
    }

    return success(value);
  };
}

export interface TrimmedOptions {
  allowEmpty?: boolean;
}

/**
 * Validates and trims whitespace from a string.
 */
export function trimmed(options: TrimmedOptions = {}): Validator<string, string> {
  const { allowEmpty = false } = options;

  return (value: string): ValidationResult<string> => {
    if (typeof value !== 'string') {
      return failure('Value must be a string');
    }

    const result = value.trim();

    if (!allowEmpty && result === '') {
      return failure('Value cannot be empty');
    }

    return success(result);
  };
}
