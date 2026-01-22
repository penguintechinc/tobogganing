/**
 * gRPC security interceptors for authentication, rate limiting, and audit logging.
 */

import * as grpc from '@grpc/grpc-js';
import * as jwt from 'jsonwebtoken';
import { v4 as uuidv4 } from 'uuid';

/**
 * JWT authentication interceptor for gRPC servers.
 *
 * Validates JWT tokens in metadata and sets user context.
 *
 * @example
 * ```typescript
 * const server = createServer([
 *   authInterceptor('your-secret-key', ['/health.Check']),
 * ]);
 * ```
 */
export function authInterceptor(
  secretKey: string,
  publicMethods: string[] = []
): grpc.Interceptor {
  const publicMethodSet = new Set(publicMethods);

  return (options, nextCall) => {
    return new grpc.InterceptingCall(nextCall(options), {
      start(metadata, listener, next) {
        const method = options.method_definition.path;

        // Skip auth for public methods
        if (publicMethodSet.has(method)) {
          next(metadata, listener);
          return;
        }

        // Extract token from metadata
        const authHeader = metadata.get('authorization')[0] as string;

        if (!authHeader || !authHeader.startsWith('Bearer ')) {
          const error = new Error('Missing or invalid authorization header');
          listener.onReceiveStatus({
            code: grpc.status.UNAUTHENTICATED,
            details: error.message,
            metadata: new grpc.Metadata(),
          });
          return;
        }

        const token = authHeader.substring(7); // Remove 'Bearer ' prefix

        try {
          // Validate JWT token
          const payload = jwt.verify(token, secretKey) as jwt.JwtPayload;

          // Add user info to metadata
          if (payload.sub) {
            metadata.set('user-id', payload.sub);
            console.log(`Authenticated request to ${method} from user ${payload.sub}`);
          }

          next(metadata, listener);
        } catch (error) {
          console.warn(`Invalid token for ${method}:`, error);
          listener.onReceiveStatus({
            code: grpc.status.UNAUTHENTICATED,
            details: 'Invalid token',
            metadata: new grpc.Metadata(),
          });
        }
      },
    });
  };
}

interface RateLimitEntry {
  count: number;
  windowStart: number;
}

/**
 * Rate limiting interceptor with per-client limits.
 *
 * Implements sliding window rate limiting.
 *
 * @example
 * ```typescript
 * const server = createServer([
 *   rateLimitInterceptor(100, true),
 * ]);
 * ```
 */
export function rateLimitInterceptor(
  requestsPerMinute: number = 100,
  perUser: boolean = true
): grpc.Interceptor {
  const limits = new Map<string, RateLimitEntry>();

  return (options, nextCall) => {
    return new grpc.InterceptingCall(nextCall(options), {
      start(metadata, listener, next) {
        // Determine client identifier
        let clientId = 'anonymous';

        if (perUser) {
          // Extract user from token
          const authHeader = metadata.get('authorization')[0] as string;
          if (authHeader && authHeader.startsWith('Bearer ')) {
            try {
              const token = authHeader.substring(7);
              const payload = jwt.decode(token) as jwt.JwtPayload;
              if (payload?.sub) {
                clientId = payload.sub;
              }
            } catch (error) {
              // Ignore decode errors
            }
          }
        } else {
          // Use peer address (IP)
          const forwarded = metadata.get('x-forwarded-for')[0] as string;
          if (forwarded) {
            clientId = forwarded;
          }
        }

        // Check rate limit
        const currentTime = Date.now();
        let entry = limits.get(clientId);

        if (!entry) {
          entry = { count: 0, windowStart: currentTime };
          limits.set(clientId, entry);
        }

        // Reset window if expired
        if (currentTime - entry.windowStart >= 60000) {
          entry.count = 0;
          entry.windowStart = currentTime;
        }

        // Check limit
        if (entry.count >= requestsPerMinute) {
          console.warn(`Rate limit exceeded for ${clientId}`, {
            requests: entry.count,
          });

          listener.onReceiveStatus({
            code: grpc.status.RESOURCE_EXHAUSTED,
            details: 'Rate limit exceeded',
            metadata: new grpc.Metadata(),
          });
          return;
        }

        // Increment counter
        entry.count++;

        next(metadata, listener);
      },
    });
  };
}

/**
 * Audit logging interceptor for request/response tracking.
 *
 * Logs method calls, duration, and status codes.
 *
 * @example
 * ```typescript
 * const server = createServer([
 *   auditInterceptor(),
 * ]);
 * ```
 */
export function auditInterceptor(): grpc.Interceptor {
  return (options, nextCall) => {
    const method = options.method_definition.path;
    const startTime = Date.now();

    return new grpc.InterceptingCall(nextCall(options), {
      start(metadata, listener, next) {
        // Get correlation ID
        const correlationId = (metadata.get('x-correlation-id')[0] as string) || 'unknown';

        console.log(`gRPC request started: ${method}`, {
          method,
          correlationId,
        });

        // Wrap listener to log completion
        const wrappedListener: grpc.Listener = {
          ...listener,
          onReceiveStatus(status, nextStatus) {
            const durationMs = Date.now() - startTime;

            if (status.code === grpc.status.OK) {
              console.log(`gRPC request completed: ${method}`, {
                method,
                durationMs,
                correlationId,
                status: 'OK',
              });
            } else {
              console.error(`gRPC request failed: ${method}`, {
                method,
                durationMs,
                correlationId,
                code: status.code,
                details: status.details,
              });
            }

            if (nextStatus) {
              nextStatus(status);
            }
          },
        };

        next(metadata, wrappedListener);
      },
    });
  };
}

/**
 * Correlation ID interceptor for request tracing.
 *
 * Adds or propagates correlation IDs across service calls.
 *
 * @example
 * ```typescript
 * const server = createServer([
 *   correlationInterceptor(),
 * ]);
 * ```
 */
export function correlationInterceptor(): grpc.Interceptor {
  return (options, nextCall) => {
    return new grpc.InterceptingCall(nextCall(options), {
      start(metadata, listener, next) {
        // Get or create correlation ID
        let correlationId = metadata.get('x-correlation-id')[0] as string;
        if (!correlationId) {
          correlationId = uuidv4();
          metadata.set('x-correlation-id', correlationId);
          console.debug(`Generated new correlation ID: ${correlationId}`);
        }

        next(metadata, listener);
      },
    });
  };
}
