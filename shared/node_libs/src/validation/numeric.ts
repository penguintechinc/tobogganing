/**
 * Numeric validators for input validation.
 */

import { type ValidationResult, type Validator, success, failure } from './index.js';

type NumericInput = number | string;

export interface IntOptions {
  errorMessage?: string;
}

/**
 * Validates that a value is or can be converted to an integer.
 */
export function isInt(options: IntOptions = {}): Validator<NumericInput, number> {
  const errorMessage = options.errorMessage ?? 'Value must be an integer';

  return (value: NumericInput): ValidationResult<number> => {
    if (typeof value === 'boolean') {
      return failure(errorMessage);
    }

    if (typeof value === 'number') {
      if (Number.isInteger(value)) {
        return success(value);
      }
      return failure(errorMessage);
    }

    if (typeof value === 'string') {
      // Don't allow floats in string form
      if (value.includes('.') || value.toLowerCase().includes('e')) {
        return failure(errorMessage);
      }

      const parsed = parseInt(value, 10);
      if (isNaN(parsed)) {
        return failure(errorMessage);
      }
      return success(parsed);
    }

    return failure(errorMessage);
  };
}

export interface FloatOptions {
  errorMessage?: string;
}

/**
 * Validates that a value is or can be converted to a float.
 */
export function isFloat(options: FloatOptions = {}): Validator<NumericInput, number> {
  const errorMessage = options.errorMessage ?? 'Value must be a number';

  return (value: NumericInput): ValidationResult<number> => {
    if (typeof value === 'boolean') {
      return failure(errorMessage);
    }

    if (typeof value === 'number') {
      if (isNaN(value) || !isFinite(value)) {
        return failure(errorMessage);
      }
      return success(value);
    }

    if (typeof value === 'string') {
      const parsed = parseFloat(value);
      if (isNaN(parsed) || !isFinite(parsed)) {
        return failure(errorMessage);
      }
      return success(parsed);
    }

    return failure(errorMessage);
  };
}

export interface IntInRangeOptions {
  errorMessage?: string;
}

/**
 * Validates that an integer is within a specified range.
 */
export function intInRange(min: number, max: number, options: IntInRangeOptions = {}): Validator<NumericInput, number> {
  return (value: NumericInput): ValidationResult<number> => {
    const intResult = isInt().call(null, value);
    if (!intResult.isValid) {
      return intResult;
    }

    const intValue = intResult.value as number;

    if (intValue < min) {
      return failure(options.errorMessage ?? `Value must be at least ${min}`);
    }

    if (intValue > max) {
      return failure(options.errorMessage ?? `Value must be at most ${max}`);
    }

    return success(intValue);
  };
}

/**
 * Validates minimum integer value.
 */
export function intMin(min: number, options: IntInRangeOptions = {}): Validator<NumericInput, number> {
  return (value: NumericInput): ValidationResult<number> => {
    const intResult = isInt().call(null, value);
    if (!intResult.isValid) {
      return intResult;
    }

    const intValue = intResult.value as number;

    if (intValue < min) {
      return failure(options.errorMessage ?? `Value must be at least ${min}`);
    }

    return success(intValue);
  };
}

/**
 * Validates maximum integer value.
 */
export function intMax(max: number, options: IntInRangeOptions = {}): Validator<NumericInput, number> {
  return (value: NumericInput): ValidationResult<number> => {
    const intResult = isInt().call(null, value);
    if (!intResult.isValid) {
      return intResult;
    }

    const intValue = intResult.value as number;

    if (intValue > max) {
      return failure(options.errorMessage ?? `Value must be at most ${max}`);
    }

    return success(intValue);
  };
}

export interface FloatInRangeOptions {
  errorMessage?: string;
}

/**
 * Validates that a float is within a specified range.
 */
export function floatInRange(min: number, max: number, options: FloatInRangeOptions = {}): Validator<NumericInput, number> {
  return (value: NumericInput): ValidationResult<number> => {
    const floatResult = isFloat().call(null, value);
    if (!floatResult.isValid) {
      return floatResult;
    }

    const floatValue = floatResult.value as number;

    if (floatValue < min) {
      return failure(options.errorMessage ?? `Value must be at least ${min}`);
    }

    if (floatValue > max) {
      return failure(options.errorMessage ?? `Value must be at most ${max}`);
    }

    return success(floatValue);
  };
}

export interface PositiveOptions {
  allowZero?: boolean;
  errorMessage?: string;
}

/**
 * Validates that a number is positive (> 0).
 */
export function positive(options: PositiveOptions = {}): Validator<NumericInput, number> {
  const { allowZero = false } = options;

  return (value: NumericInput): ValidationResult<number> => {
    const floatResult = isFloat().call(null, value);
    if (!floatResult.isValid) {
      return floatResult;
    }

    const floatValue = floatResult.value as number;

    if (allowZero) {
      if (floatValue < 0) {
        return failure(options.errorMessage ?? 'Value must be zero or positive');
      }
    } else {
      if (floatValue <= 0) {
        return failure(options.errorMessage ?? 'Value must be positive');
      }
    }

    return success(floatValue);
  };
}

export interface NegativeOptions {
  allowZero?: boolean;
  errorMessage?: string;
}

/**
 * Validates that a number is negative (< 0).
 */
export function negative(options: NegativeOptions = {}): Validator<NumericInput, number> {
  const { allowZero = false } = options;

  return (value: NumericInput): ValidationResult<number> => {
    const floatResult = isFloat().call(null, value);
    if (!floatResult.isValid) {
      return floatResult;
    }

    const floatValue = floatResult.value as number;

    if (allowZero) {
      if (floatValue > 0) {
        return failure(options.errorMessage ?? 'Value must be zero or negative');
      }
    } else {
      if (floatValue >= 0) {
        return failure(options.errorMessage ?? 'Value must be negative');
      }
    }

    return success(floatValue);
  };
}
