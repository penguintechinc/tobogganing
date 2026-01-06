/**
 * DateTime validators for input validation.
 */

import { type ValidationResult, type Validator, success, failure } from './index.js';

type DateInput = string | Date;

export interface DateOptions {
  format?: string;
  errorMessage?: string;
}

/**
 * Validates that a value is or can be parsed as a date.
 * Uses ISO 8601 format (YYYY-MM-DD) by default.
 */
export function date(options: DateOptions = {}): Validator<DateInput, Date> {
  const format = options.format ?? 'YYYY-MM-DD';

  const getErrorMessage = (): string => {
    return options.errorMessage ?? `Invalid date format. Expected: ${format}`;
  };

  return (value: DateInput): ValidationResult<Date> => {
    if (value instanceof Date) {
      if (isNaN(value.getTime())) {
        return failure(getErrorMessage());
      }
      return success(value);
    }

    if (typeof value !== 'string') {
      return failure('Value must be a string or Date');
    }

    const dateStr = value.trim();
    if (dateStr === '') {
      return failure(getErrorMessage());
    }

    // Try to parse based on format
    let parsed: Date;

    if (format === 'YYYY-MM-DD') {
      // ISO 8601 date format
      const match = dateStr.match(/^(\d{4})-(\d{2})-(\d{2})$/);
      if (!match) {
        return failure(getErrorMessage());
      }

      const [, year, month, day] = match;
      parsed = new Date(parseInt(year!, 10), parseInt(month!, 10) - 1, parseInt(day!, 10));

      // Validate the date is real (handles invalid dates like 2024-02-30)
      if (
        parsed.getFullYear() !== parseInt(year!, 10) ||
        parsed.getMonth() !== parseInt(month!, 10) - 1 ||
        parsed.getDate() !== parseInt(day!, 10)
      ) {
        return failure(getErrorMessage());
      }
    } else {
      // Try native Date parsing for other formats
      parsed = new Date(dateStr);
      if (isNaN(parsed.getTime())) {
        return failure(getErrorMessage());
      }
    }

    return success(parsed);
  };
}

export interface DateTimeOptions {
  format?: string;
  errorMessage?: string;
}

/**
 * Validates that a value is or can be parsed as a datetime.
 * Uses ISO 8601 format (YYYY-MM-DDTHH:mm:ss) by default.
 */
export function dateTime(options: DateTimeOptions = {}): Validator<DateInput, Date> {
  const format = options.format ?? 'YYYY-MM-DDTHH:mm:ss';

  const getErrorMessage = (): string => {
    return options.errorMessage ?? `Invalid datetime format. Expected: ${format}`;
  };

  return (value: DateInput): ValidationResult<Date> => {
    if (value instanceof Date) {
      if (isNaN(value.getTime())) {
        return failure(getErrorMessage());
      }
      return success(value);
    }

    if (typeof value !== 'string') {
      return failure('Value must be a string or Date');
    }

    const dateStr = value.trim();
    if (dateStr === '') {
      return failure(getErrorMessage());
    }

    // Try to parse based on format
    let parsed: Date;

    if (format === 'YYYY-MM-DDTHH:mm:ss') {
      // ISO 8601 datetime format (without timezone)
      const match = dateStr.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})$/);
      if (!match) {
        return failure(getErrorMessage());
      }

      const [, year, month, day, hour, minute, second] = match;
      parsed = new Date(
        parseInt(year!, 10),
        parseInt(month!, 10) - 1,
        parseInt(day!, 10),
        parseInt(hour!, 10),
        parseInt(minute!, 10),
        parseInt(second!, 10)
      );

      if (isNaN(parsed.getTime())) {
        return failure(getErrorMessage());
      }
    } else {
      // Try native Date parsing for other formats
      parsed = new Date(dateStr);
      if (isNaN(parsed.getTime())) {
        return failure(getErrorMessage());
      }
    }

    return success(parsed);
  };
}

export interface TimeOptions {
  format?: string;
  errorMessage?: string;
}

/**
 * Validates that a value is or can be parsed as a time.
 * Uses HH:mm:ss format by default.
 */
export function time(options: TimeOptions = {}): Validator<string, string> {
  const format = options.format ?? 'HH:mm:ss';

  const getErrorMessage = (): string => {
    return options.errorMessage ?? `Invalid time format. Expected: ${format}`;
  };

  return (value: string): ValidationResult<string> => {
    if (typeof value !== 'string') {
      return failure('Value must be a string');
    }

    const timeStr = value.trim();
    if (timeStr === '') {
      return failure(getErrorMessage());
    }

    if (format === 'HH:mm:ss') {
      const match = timeStr.match(/^(\d{2}):(\d{2}):(\d{2})$/);
      if (!match) {
        return failure(getErrorMessage());
      }

      const [, hour, minute, second] = match;
      const h = parseInt(hour!, 10);
      const m = parseInt(minute!, 10);
      const s = parseInt(second!, 10);

      if (h < 0 || h > 23 || m < 0 || m > 59 || s < 0 || s > 59) {
        return failure(getErrorMessage());
      }

      return success(timeStr);
    }

    if (format === 'HH:mm') {
      const match = timeStr.match(/^(\d{2}):(\d{2})$/);
      if (!match) {
        return failure(getErrorMessage());
      }

      const [, hour, minute] = match;
      const h = parseInt(hour!, 10);
      const m = parseInt(minute!, 10);

      if (h < 0 || h > 23 || m < 0 || m > 59) {
        return failure(getErrorMessage());
      }

      return success(timeStr);
    }

    // For other formats, just validate it looks like a time
    if (!/^\d{1,2}:\d{2}(:\d{2})?$/.test(timeStr)) {
      return failure(getErrorMessage());
    }

    return success(timeStr);
  };
}

export interface DateInRangeOptions {
  format?: string;
  errorMessage?: string;
}

/**
 * Validates that a date is within a specified range.
 */
export function dateInRange(
  minDate: Date | null,
  maxDate: Date | null,
  options: DateInRangeOptions = {}
): Validator<DateInput, Date> {
  const format = options.format ?? 'YYYY-MM-DD';

  return (value: DateInput): ValidationResult<Date> => {
    const dateResult = date({ format })(value);
    if (!dateResult.isValid) {
      return dateResult;
    }

    const dateValue = dateResult.value as Date;

    if (minDate !== null && dateValue < minDate) {
      return failure(options.errorMessage ?? `Date must be on or after ${minDate.toISOString().split('T')[0]}`);
    }

    if (maxDate !== null && dateValue > maxDate) {
      return failure(options.errorMessage ?? `Date must be on or before ${maxDate.toISOString().split('T')[0]}`);
    }

    return success(dateValue);
  };
}

/**
 * Validates that a date is after a minimum date.
 */
export function dateAfter(minDate: Date, options: DateInRangeOptions = {}): Validator<DateInput, Date> {
  return dateInRange(minDate, null, options);
}

/**
 * Validates that a date is before a maximum date.
 */
export function dateBefore(maxDate: Date, options: DateInRangeOptions = {}): Validator<DateInput, Date> {
  return dateInRange(null, maxDate, options);
}

/**
 * Validates ISO 8601 datetime with timezone (RFC 3339).
 */
export function iso8601(options: DateTimeOptions = {}): Validator<DateInput, Date> {
  const errorMessage = options.errorMessage ?? 'Invalid ISO 8601 datetime';

  return (value: DateInput): ValidationResult<Date> => {
    if (value instanceof Date) {
      if (isNaN(value.getTime())) {
        return failure(errorMessage);
      }
      return success(value);
    }

    if (typeof value !== 'string') {
      return failure('Value must be a string or Date');
    }

    const dateStr = value.trim();
    if (dateStr === '') {
      return failure(errorMessage);
    }

    // ISO 8601 with optional timezone
    const parsed = new Date(dateStr);
    if (isNaN(parsed.getTime())) {
      return failure(errorMessage);
    }

    return success(parsed);
  };
}
