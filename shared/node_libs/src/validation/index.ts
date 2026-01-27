/**
 * Validation module - Input validators similar to PyDAL.
 *
 * Provides validators that follow a consistent pattern:
 * - Each validator returns a ValidationResult with success/failure status
 * - Validators can be chained using the chain function
 * - Error messages are human-readable for API responses
 *
 * @example
 * ```typescript
 * import { chain, notEmpty, length, email } from '@penguin/node_libs/validation';
 *
 * const validator = chain(notEmpty(), length(3, 255), email());
 * const result = validator(emailValue);
 * if (!result.isValid) {
 *     return res.status(400).json({ error: result.error });
 * }
 * ```
 *
 * @packageDocumentation
 */

// Types
export interface ValidationResult<T = unknown> {
  isValid: boolean;
  value: T | null;
  error: string | null;
}

export type Validator<T = unknown, V = unknown> = (value: T) => ValidationResult<V>;

// Result creators
export function success<T>(value: T): ValidationResult<T> {
  return { isValid: true, value, error: null };
}

export function failure(error: string): ValidationResult<never> {
  return { isValid: false, value: null, error };
}

// Chain validators
export function chain<T>(...validators: Validator<unknown, unknown>[]): Validator<T, unknown> {
  return (value: T): ValidationResult<unknown> => {
    let currentValue: unknown = value;

    for (const validator of validators) {
      const result = validator(currentValue);
      if (!result.isValid) {
        return result;
      }
      currentValue = result.value;
    }

    return success(currentValue);
  };
}

// Unwrap helpers
export function unwrap<T>(result: ValidationResult<T>): T {
  if (!result.isValid || result.value === null) {
    throw new Error(`Validation failed: ${result.error ?? 'Unknown error'}`);
  }
  return result.value;
}

export function unwrapOr<T>(result: ValidationResult<T>, defaultValue: T): T {
  if (result.isValid && result.value !== null) {
    return result.value;
  }
  return defaultValue;
}

// Export all validators
export * from './string.js';
export * from './numeric.js';
export * from './network.js';
export * from './datetime.js';
export * from './password.js';
