/**
 * HTTP utilities
 *
 * Provides:
 * - correlation: Request ID/correlation middleware
 * - client: Resilient HTTP client with retries
 */

// Correlation ID utilities
export {
  generateCorrelationId,
  getCorrelationId,
  correlationMiddleware,
  HEADER_X_CORRELATION_ID,
  HEADER_X_REQUEST_ID,
} from './correlation';

// HTTP client
export {
  HttpClient,
  CircuitState,
  type RetryConfig,
  type CircuitBreakerConfig,
  type HttpClientConfig,
} from './client';
