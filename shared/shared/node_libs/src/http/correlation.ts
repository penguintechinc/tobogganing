/**
 * Request correlation ID middleware for Express applications.
 *
 * Provides correlation ID generation and propagation for request tracing
 * across microservices.
 */

import { Request, Response, NextFunction } from 'express';
import { v4 as uuidv4 } from 'uuid';

/**
 * Headers used for correlation ID propagation.
 */
export const HEADER_X_CORRELATION_ID = 'X-Correlation-ID';
export const HEADER_X_REQUEST_ID = 'X-Request-ID';

/**
 * Symbol for storing correlation ID in request object.
 */
const CORRELATION_ID_SYMBOL = Symbol.for('correlationId');

/**
 * Generate a new correlation ID using UUID v4.
 *
 * @returns A new UUID v4 string suitable for correlation tracking
 */
export function generateCorrelationId(): string {
  return uuidv4();
}

/**
 * Extract correlation ID from request headers or generate new one.
 *
 * Checks X-Correlation-ID and X-Request-ID headers in order.
 *
 * @param req - Express request object
 * @returns Extracted or newly generated correlation ID
 */
function extractCorrelationId(req: Request): string {
  // Check X-Correlation-ID first (preferred)
  const correlationId = req.get(HEADER_X_CORRELATION_ID);
  if (correlationId) {
    return correlationId;
  }

  // Fall back to X-Request-ID
  const requestId = req.get(HEADER_X_REQUEST_ID);
  if (requestId) {
    return requestId;
  }

  // Generate new correlation ID
  return generateCorrelationId();
}

/**
 * Get the correlation ID from the request object.
 *
 * @param req - Express request object
 * @returns Current correlation ID or undefined if not set
 */
export function getCorrelationId(req: Request): string | undefined {
  return (req as any)[CORRELATION_ID_SYMBOL];
}

/**
 * Set the correlation ID on the request object.
 *
 * @param req - Express request object
 * @param correlationId - Correlation ID to set
 */
function setCorrelationId(req: Request, correlationId: string): void {
  (req as any)[CORRELATION_ID_SYMBOL] = correlationId;
}

/**
 * Express middleware for correlation ID handling.
 *
 * Extracts correlation IDs from incoming requests or generates new ones,
 * stores them in request object, and adds them to response headers.
 *
 * Example:
 * ```typescript
 * import express from 'express';
 * import { correlationMiddleware, getCorrelationId } from './correlation';
 *
 * const app = express();
 * app.use(correlationMiddleware());
 *
 * app.get('/api/v1/example', (req, res) => {
 *   const correlationId = getCorrelationId(req);
 *   console.log(`Processing request with correlation ID: ${correlationId}`);
 *   res.json({ status: 'ok' });
 * });
 * ```
 *
 * @returns Express middleware function
 */
export function correlationMiddleware() {
  return (req: Request, res: Response, next: NextFunction): void => {
    // Extract or generate correlation ID
    const correlationId = extractCorrelationId(req);

    // Store in request object
    setCorrelationId(req, correlationId);

    // Add to response headers
    res.setHeader(HEADER_X_CORRELATION_ID, correlationId);
    res.setHeader(HEADER_X_REQUEST_ID, correlationId);

    // Continue processing
    next();
  };
}
