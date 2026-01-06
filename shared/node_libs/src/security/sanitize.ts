/**
 * HTML/XSS sanitization utilities
 * Provides functions to sanitize user input and prevent XSS attacks
 */

import * as path from 'path';

/**
 * HTML entity map for escaping
 */
const HTML_ENTITIES: Record<string, string> = {
  '&': '&amp;',
  '<': '&lt;',
  '>': '&gt;',
  '"': '&quot;',
  "'": '&#x27;',
  '/': '&#x2F;',
};

/**
 * Escape HTML entities to prevent XSS
 * @param input - String to escape
 * @returns Escaped string safe for HTML insertion
 */
export function escapeHtml(input: string): string {
  if (typeof input !== 'string') {
    return String(input);
  }
  return input.replace(/[&<>"'/]/g, (char) => HTML_ENTITIES[char] || char);
}

/**
 * Sanitize HTML by removing potentially dangerous tags and attributes
 * Basic implementation - for production use a library like DOMPurify
 * @param html - HTML string to sanitize
 * @returns Sanitized HTML string
 */
export function sanitizeHtml(html: string): string {
  if (typeof html !== 'string') {
    return '';
  }

  // Remove script tags and their content
  let sanitized = html.replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, '');

  // Remove dangerous event handlers
  sanitized = sanitized.replace(/\son\w+\s*=\s*["'][^"']*["']/gi, '');
  sanitized = sanitized.replace(/\son\w+\s*=\s*[^\s>]*/gi, '');

  // Remove javascript: protocol
  sanitized = sanitized.replace(/javascript:/gi, '');

  // Remove data: protocol (can be used for XSS)
  sanitized = sanitized.replace(/data:text\/html/gi, '');

  // Remove iframe tags
  sanitized = sanitized.replace(/<iframe\b[^<]*(?:(?!<\/iframe>)<[^<]*)*<\/iframe>/gi, '');

  // Remove object and embed tags
  sanitized = sanitized.replace(/<(object|embed)\b[^<]*(?:(?!<\/\1>)<[^<]*)*<\/\1>/gi, '');

  return sanitized;
}

/**
 * Sanitize file paths to prevent directory traversal attacks
 * @param inputPath - Path to sanitize
 * @param allowedBase - Base directory to restrict paths to (optional)
 * @returns Sanitized path or null if path traversal detected
 */
export function sanitizePath(inputPath: string, allowedBase?: string): string | null {
  if (typeof inputPath !== 'string') {
    return null;
  }

  // Normalize the path to resolve .. and .
  const normalized = path.normalize(inputPath);

  // Check for path traversal attempts
  if (normalized.includes('..') || normalized.startsWith('/')) {
    return null;
  }

  // If base directory provided, ensure path stays within it
  if (allowedBase) {
    const resolvedPath = path.resolve(allowedBase, normalized);
    const resolvedBase = path.resolve(allowedBase);

    // Ensure resolved path starts with base directory
    if (!resolvedPath.startsWith(resolvedBase)) {
      return null;
    }

    return resolvedPath;
  }

  return normalized;
}

/**
 * Sanitize user input for database queries (basic SQL injection prevention)
 * NOTE: Always use parameterized queries instead of string concatenation
 * This is a last-resort defense layer only
 * @param input - Input to sanitize
 * @returns Sanitized input
 */
export function sanitizeSqlInput(input: string): string {
  if (typeof input !== 'string') {
    return String(input);
  }

  // Remove common SQL injection patterns
  return input
    .replace(/['";]/g, '') // Remove quotes and semicolons
    .replace(/--/g, '') // Remove SQL comments
    .replace(/\/\*/g, '') // Remove multi-line comment start
    .replace(/\*\//g, '') // Remove multi-line comment end
    .replace(/xp_/gi, '') // Remove xp_ commands (MSSQL)
    .replace(/EXEC(UTE)?/gi, '') // Remove EXEC commands
    .replace(/UNION/gi, '') // Remove UNION
    .replace(/SELECT/gi, '') // Remove SELECT
    .replace(/INSERT/gi, '') // Remove INSERT
    .replace(/UPDATE/gi, '') // Remove UPDATE
    .replace(/DELETE/gi, '') // Remove DELETE
    .replace(/DROP/gi, ''); // Remove DROP
}

/**
 * Sanitize and validate email addresses
 * @param email - Email to validate
 * @returns Sanitized email or null if invalid
 */
export function sanitizeEmail(email: string): string | null {
  if (typeof email !== 'string') {
    return null;
  }

  const trimmed = email.trim().toLowerCase();

  // Basic email validation regex
  const emailRegex = /^[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}$/i;

  if (!emailRegex.test(trimmed)) {
    return null;
  }

  // Additional length validation
  if (trimmed.length > 254) {
    return null;
  }

  return trimmed;
}

/**
 * Sanitize URL to prevent javascript: and data: protocols
 * @param url - URL to sanitize
 * @returns Sanitized URL or null if dangerous
 */
export function sanitizeUrl(url: string): string | null {
  if (typeof url !== 'string') {
    return null;
  }

  const trimmed = url.trim();

  // Check for dangerous protocols
  const dangerousProtocols = /^(javascript|data|vbscript):/i;
  if (dangerousProtocols.test(trimmed)) {
    return null;
  }

  // Ensure URL starts with safe protocol or is relative
  const safeProtocols = /^(https?|ftp|mailto):/i;
  if (!safeProtocols.test(trimmed) && !trimmed.startsWith('/') && !trimmed.startsWith('.')) {
    return null;
  }

  return trimmed;
}
