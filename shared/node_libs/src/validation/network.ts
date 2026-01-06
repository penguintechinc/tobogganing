/**
 * Network validators for input validation (email, URL, IP, hostname).
 */

import { type ValidationResult, type Validator, success, failure } from './index.js';

export interface EmailOptions {
  normalize?: boolean;
  errorMessage?: string;
}

/**
 * Validates that a string is a valid email address.
 * Uses RFC 5322 compliant regex pattern.
 */
export function email(options: EmailOptions = {}): Validator<string, string> {
  const { normalize = true } = options;
  const errorMessage = options.errorMessage ?? 'Invalid email address';

  // RFC 5322 compliant email regex (simplified but robust)
  const emailRegex = /^[a-zA-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+$/;

  return (value: string): ValidationResult<string> => {
    if (typeof value !== 'string') {
      return failure('Value must be a string');
    }

    const emailStr = value.trim();
    if (emailStr === '') {
      return failure(errorMessage);
    }

    // Check length constraints
    if (emailStr.length > 254) {
      return failure(errorMessage);
    }

    // Check local part length
    const atIndex = emailStr.indexOf('@');
    if (atIndex === -1 || atIndex > 64) {
      return failure(errorMessage);
    }

    if (!emailRegex.test(emailStr)) {
      return failure(errorMessage);
    }

    return success(normalize ? emailStr.toLowerCase() : emailStr);
  };
}

export interface UrlOptions {
  requireTld?: boolean;
  allowedSchemes?: string[];
  errorMessage?: string;
}

/**
 * Validates that a string is a valid URL.
 */
export function url(options: UrlOptions = {}): Validator<string, string> {
  const {
    requireTld = true,
    allowedSchemes = ['http', 'https'],
  } = options;
  const errorMessage = options.errorMessage ?? 'Invalid URL';

  const schemeSet = new Set(allowedSchemes.map(s => s.toLowerCase()));

  return (value: string): ValidationResult<string> => {
    if (typeof value !== 'string') {
      return failure('Value must be a string');
    }

    const urlStr = value.trim();
    if (urlStr === '') {
      return failure(errorMessage);
    }

    let parsed: URL;
    try {
      parsed = new URL(urlStr);
    } catch {
      return failure(errorMessage);
    }

    // Check scheme
    const scheme = parsed.protocol.replace(':', '').toLowerCase();
    if (!schemeSet.has(scheme)) {
      return failure(`URL scheme must be one of: ${allowedSchemes.join(', ')}`);
    }

    // Check hostname
    if (!parsed.hostname) {
      return failure(errorMessage);
    }

    // Check for TLD if required
    if (requireTld) {
      const hostname = parsed.hostname.toLowerCase();
      if (!hostname.includes('.') && hostname !== 'localhost') {
        return failure(errorMessage);
      }
    }

    return success(urlStr);
  };
}

export interface IpAddressOptions {
  version?: 4 | 6;
  errorMessage?: string;
}

/**
 * Validates that a string is a valid IP address.
 */
export function ipAddress(options: IpAddressOptions = {}): Validator<string, string> {
  const { version } = options;

  // IPv4 regex
  const ipv4Regex = /^(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;

  // Simplified IPv6 regex (covers most common formats)
  const ipv6Regex = /^(?:(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}|(?:[0-9a-fA-F]{1,4}:){1,7}:|(?:[0-9a-fA-F]{1,4}:){1,6}:[0-9a-fA-F]{1,4}|(?:[0-9a-fA-F]{1,4}:){1,5}(?::[0-9a-fA-F]{1,4}){1,2}|(?:[0-9a-fA-F]{1,4}:){1,4}(?::[0-9a-fA-F]{1,4}){1,3}|(?:[0-9a-fA-F]{1,4}:){1,3}(?::[0-9a-fA-F]{1,4}){1,4}|(?:[0-9a-fA-F]{1,4}:){1,2}(?::[0-9a-fA-F]{1,4}){1,5}|[0-9a-fA-F]{1,4}:(?::[0-9a-fA-F]{1,4}){1,6}|:(?:(?::[0-9a-fA-F]{1,4}){1,7}|:)|fe80:(?::[0-9a-fA-F]{0,4}){0,4}%[0-9a-zA-Z]+|::(?:ffff(?::0{1,4})?:)?(?:(?:25[0-5]|(?:2[0-4]|1?[0-9])?[0-9])\.){3}(?:25[0-5]|(?:2[0-4]|1?[0-9])?[0-9])|(?:[0-9a-fA-F]{1,4}:){1,4}:(?:(?:25[0-5]|(?:2[0-4]|1?[0-9])?[0-9])\.){3}(?:25[0-5]|(?:2[0-4]|1?[0-9])?[0-9]))$/;

  const getErrorMessage = (): string => {
    if (options.errorMessage) return options.errorMessage;
    if (version === 4) return 'Value must be a valid IPv4 address';
    if (version === 6) return 'Value must be a valid IPv6 address';
    return 'Value must be a valid IP address';
  };

  return (value: string): ValidationResult<string> => {
    if (typeof value !== 'string') {
      return failure('Value must be a string');
    }

    const ipStr = value.trim();
    if (ipStr === '') {
      return failure(getErrorMessage());
    }

    const isIPv4 = ipv4Regex.test(ipStr);
    const isIPv6 = ipv6Regex.test(ipStr);

    if (!isIPv4 && !isIPv6) {
      return failure(getErrorMessage());
    }

    if (version === 4 && !isIPv4) {
      return failure('Value must be a valid IPv4 address');
    }

    if (version === 6 && !isIPv6) {
      return failure('Value must be a valid IPv6 address');
    }

    return success(ipStr);
  };
}

export interface HostnameOptions {
  allowIp?: boolean;
  requireTld?: boolean;
  errorMessage?: string;
}

/**
 * Validates that a string is a valid hostname.
 */
export function hostname(options: HostnameOptions = {}): Validator<string, string> {
  const {
    allowIp = false,
    requireTld = false,
  } = options;
  const errorMessage = options.errorMessage ?? 'Invalid hostname';

  // RFC 1123 hostname pattern
  const hostnameRegex = /^(?![-])[a-zA-Z0-9-]{1,63}(?<![])(?:\.(?![]))[a-zA-Z0-9-]{1,63}(?<![]))*$/;

  return (value: string): ValidationResult<string> => {
    if (typeof value !== 'string') {
      return failure('Value must be a string');
    }

    const hostStr = value.trim().toLowerCase();
    if (hostStr === '') {
      return failure(errorMessage);
    }

    // Check total length
    if (hostStr.length > 253) {
      return failure(errorMessage);
    }

    // Check if it's an IP address
    if (allowIp) {
      const ipResult = ipAddress()(hostStr);
      if (ipResult.isValid) {
        return success(hostStr);
      }
    }

    // Validate hostname format
    // Simpler validation: each label 1-63 chars, alphanumeric and hyphens, no leading/trailing hyphens
    const labels = hostStr.split('.');
    for (const label of labels) {
      if (label.length === 0 || label.length > 63) {
        return failure(errorMessage);
      }
      if (label.startsWith('-') || label.endsWith('-')) {
        return failure(errorMessage);
      }
      if (!/^[a-z0-9-]+$/.test(label)) {
        return failure(errorMessage);
      }
    }

    // Check TLD requirement
    if (requireTld && !hostStr.includes('.')) {
      return failure('Hostname must have a top-level domain');
    }

    return success(hostStr);
  };
}
