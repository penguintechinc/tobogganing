import { createCipheriv, createDecipheriv, randomBytes } from 'crypto';

const ALGORITHM = 'aes-256-gcm';
const IV_LENGTH = 12; // 96-bit IV for GCM
const AUTH_TAG_LENGTH = 16; // 128-bit authentication tag

/**
 * Encrypts plaintext using AES-256-GCM with the provided key.
 * Key must be 32 bytes for AES-256.
 * Returns base64-encoded ciphertext with IV and auth tag prepended.
 */
export function encrypt(plaintext: string, key: Buffer): string {
  if (key.length !== 32) {
    throw new Error(`Key must be 32 bytes for AES-256, got ${key.length} bytes`);
  }

  if (!plaintext) {
    throw new Error('Plaintext cannot be empty');
  }

  const iv = randomBytes(IV_LENGTH);
  const cipher = createCipheriv(ALGORITHM, key, iv);

  let encrypted = cipher.update(plaintext, 'utf8', 'base64');
  encrypted += cipher.final('base64');

  const authTag = cipher.getAuthTag();

  // Combine: IV + AuthTag + Ciphertext
  const combined = Buffer.concat([
    iv,
    authTag,
    Buffer.from(encrypted, 'base64'),
  ]);

  return combined.toString('base64');
}

/**
 * Decrypts base64-encoded ciphertext using AES-256-GCM with the provided key.
 * Key must be 32 bytes for AES-256.
 * Expects ciphertext to have IV and auth tag prepended (as produced by encrypt).
 */
export function decrypt(ciphertext: string, key: Buffer): string {
  if (key.length !== 32) {
    throw new Error(`Key must be 32 bytes for AES-256, got ${key.length} bytes`);
  }

  if (!ciphertext) {
    throw new Error('Ciphertext cannot be empty');
  }

  const data = Buffer.from(ciphertext, 'base64');

  if (data.length < IV_LENGTH + AUTH_TAG_LENGTH) {
    throw new Error(
      `Ciphertext too short: expected at least ${IV_LENGTH + AUTH_TAG_LENGTH} bytes, got ${data.length}`
    );
  }

  // Extract: IV + AuthTag + Ciphertext
  const iv = data.subarray(0, IV_LENGTH);
  const authTag = data.subarray(IV_LENGTH, IV_LENGTH + AUTH_TAG_LENGTH);
  const encryptedData = data.subarray(IV_LENGTH + AUTH_TAG_LENGTH);

  const decipher = createDecipheriv(ALGORITHM, key, iv);
  decipher.setAuthTag(authTag);

  let decrypted = decipher.update(encryptedData);
  decrypted = Buffer.concat([decrypted, decipher.final()]);

  return decrypted.toString('utf8');
}
