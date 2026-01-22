/**
 * @penguin/node_libs - Shared Node.js/TypeScript libraries for secure application development.
 *
 * This package provides "batteries included" security-focused utilities:
 * - validation: Input validators similar to PyDAL
 * - security: Rate limiting, CSRF, secure headers, sanitization
 * - crypto: Token generation, hashing, encryption
 * - http: Request correlation, resilient HTTP client
 * - grpc: gRPC server/client with security interceptors
 *
 * @packageDocumentation
 */

export * from './validation/index.js';
export * from './security/index.js';

// Re-export version
export const VERSION = '1.0.0';
