import { randomBytes } from 'crypto';

/**
 * Generates a cryptographically secure random token of the specified byte length.
 * Returns hex-encoded string.
 */
export function generateToken(length: number): string {
  if (length <= 0) {
    throw new Error(`Token length must be positive, got ${length}`);
  }

  return randomBytes(length).toString('hex');
}

/**
 * Generates a cryptographically secure random token of the specified byte length.
 * Returns URL-safe base64 encoded string (without padding).
 */
export function generateUrlSafeToken(length: number): string {
  if (length <= 0) {
    throw new Error(`Token length must be positive, got ${length}`);
  }

  return randomBytes(length)
    .toString('base64')
    .replace(/\+/g, '-')
    .replace(/\//g, '_')
    .replace(/=/g, '');
}
