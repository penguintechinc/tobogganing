/**
 * Password validators for input validation.
 */

import { type ValidationResult, type Validator, success, failure } from './index.js';

export interface PasswordOptions {
  minLength?: number;
  maxLength?: number;
  requireUppercase?: boolean;
  requireLowercase?: boolean;
  requireDigit?: boolean;
  requireSpecial?: boolean;
  specialChars?: string;
  disallowSpaces?: boolean;
}

const DEFAULT_OPTIONS: Required<PasswordOptions> = {
  minLength: 8,
  maxLength: 128,
  requireUppercase: true,
  requireLowercase: true,
  requireDigit: true,
  requireSpecial: true,
  specialChars: '!@#$%^&*()_+-=[]{}|;:,.<>?~`',
  disallowSpaces: true,
};

/**
 * Returns weak password options (min 6 chars, no special requirements).
 */
export function weakPasswordOptions(): PasswordOptions {
  return {
    minLength: 6,
    requireUppercase: false,
    requireLowercase: false,
    requireDigit: false,
    requireSpecial: false,
  };
}

/**
 * Returns moderate password options (min 8 chars, letters and digits).
 */
export function moderatePasswordOptions(): PasswordOptions {
  return {
    minLength: 8,
    requireUppercase: true,
    requireLowercase: true,
    requireDigit: true,
    requireSpecial: false,
  };
}

/**
 * Returns strong password options (min 12 chars, all character types).
 */
export function strongPasswordOptions(): PasswordOptions {
  return {
    minLength: 12,
    requireUppercase: true,
    requireLowercase: true,
    requireDigit: true,
    requireSpecial: true,
  };
}

/**
 * Returns enterprise password options (min 16 chars, all character types).
 */
export function enterprisePasswordOptions(): PasswordOptions {
  return {
    minLength: 16,
    maxLength: 256,
    requireUppercase: true,
    requireLowercase: true,
    requireDigit: true,
    requireSpecial: true,
  };
}

export interface StrongPasswordValidatorOptions extends PasswordOptions {
  errorMessage?: string;
}

/**
 * Validates password strength based on configurable requirements.
 */
export function strongPassword(options: StrongPasswordValidatorOptions = {}): Validator<string, string> {
  const opts: Required<PasswordOptions> = { ...DEFAULT_OPTIONS, ...options };

  return (value: string): ValidationResult<string> => {
    if (typeof value !== 'string') {
      return failure('Password must be a string');
    }

    const errors: string[] = [];

    // Length checks
    if (value.length < opts.minLength) {
      errors.push(`Password must be at least ${opts.minLength} characters`);
    }

    if (value.length > opts.maxLength) {
      errors.push(`Password must be at most ${opts.maxLength} characters`);
    }

    // Space check
    if (opts.disallowSpaces && value.includes(' ')) {
      errors.push('Password cannot contain spaces');
    }

    // Character type checks
    if (opts.requireUppercase && !/[A-Z]/.test(value)) {
      errors.push('Password must contain at least one uppercase letter');
    }

    if (opts.requireLowercase && !/[a-z]/.test(value)) {
      errors.push('Password must contain at least one lowercase letter');
    }

    if (opts.requireDigit && !/\d/.test(value)) {
      errors.push('Password must contain at least one digit');
    }

    if (opts.requireSpecial) {
      const specialRegex = new RegExp(`[${escapeRegex(opts.specialChars)}]`);
      if (!specialRegex.test(value)) {
        errors.push('Password must contain at least one special character');
      }
    }

    if (errors.length > 0) {
      if (options.errorMessage) {
        return failure(options.errorMessage);
      }
      return failure(errors.join('; '));
    }

    return success(value);
  };
}

/**
 * Calculates a password strength score (0-100).
 */
export function passwordStrengthScore(
  password: string,
  specialChars: string = DEFAULT_OPTIONS.specialChars
): number {
  if (!password) return 0;

  let score = 0;

  // Length contribution (up to 30 points)
  score += Math.min(password.length * 2, 30);

  // Character variety (up to 40 points)
  let variety = 0;
  if (/[a-z]/.test(password)) variety++;
  if (/[A-Z]/.test(password)) variety++;
  if (/\d/.test(password)) variety++;
  const specialRegex = new RegExp(`[${escapeRegex(specialChars)}]`);
  if (specialRegex.test(password)) variety++;
  score += variety * 10;

  // Unique character ratio (up to 20 points)
  const unique = new Set(password).size;
  const uniqueRatio = unique / password.length;
  score += Math.floor(uniqueRatio * 20);

  // No common patterns bonus (up to 10 points)
  const commonPatterns = [
    /^123/,
    /abc/i,
    /qwerty/i,
    /password/i,
    /(.)\1{2,}/, // Repeated characters
  ];

  const hasCommon = commonPatterns.some(pattern => pattern.test(password));
  if (!hasCommon) {
    score += 10;
  }

  return Math.min(score, 100);
}

/**
 * Gets a human-readable strength label for a password score.
 */
export function passwordStrengthLabel(score: number): 'very weak' | 'weak' | 'fair' | 'strong' | 'very strong' {
  if (score < 20) return 'very weak';
  if (score < 40) return 'weak';
  if (score < 60) return 'fair';
  if (score < 80) return 'strong';
  return 'very strong';
}

// Helper to escape special regex characters
function escapeRegex(str: string): string {
  return str.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}
