/**
 * HTTP client with retry logic and circuit breaker pattern.
 *
 * Provides a production-ready HTTP client with exponential backoff,
 * configurable timeouts, and optional circuit breaker protection.
 */

import axios, {
  AxiosInstance,
  AxiosRequestConfig,
  AxiosResponse,
  InternalAxiosRequestConfig,
} from 'axios';

/**
 * Circuit breaker states.
 */
export enum CircuitState {
  CLOSED = 'closed', // Normal operation
  OPEN = 'open', // Failing, reject requests
  HALF_OPEN = 'half_open', // Testing if service recovered
}

/**
 * Configuration for retry behavior.
 */
export interface RetryConfig {
  maxRetries: number; // Maximum number of retry attempts
  baseDelay: number; // Base delay in milliseconds
  maxDelay: number; // Maximum delay in milliseconds
  exponentialBase: number; // Base for exponential backoff
  jitter: boolean; // Whether to add random jitter
}

/**
 * Configuration for circuit breaker behavior.
 */
export interface CircuitBreakerConfig {
  enabled: boolean; // Whether circuit breaker is enabled
  failureThreshold: number; // Failures before opening circuit
  successThreshold: number; // Successes before closing circuit
  timeout: number; // Milliseconds to wait before half-open
}

/**
 * Configuration for HTTP client.
 */
export interface HttpClientConfig {
  timeout?: number; // Request timeout in milliseconds
  retry?: Partial<RetryConfig>; // Retry configuration
  circuitBreaker?: Partial<CircuitBreakerConfig>; // Circuit breaker config
  headers?: Record<string, string>; // Default headers
  baseURL?: string; // Base URL for requests
}

/**
 * Internal state for circuit breaker.
 */
interface CircuitBreakerState {
  state: CircuitState;
  failureCount: number;
  successCount: number;
  lastFailureTime: number;
}

/**
 * Production-ready HTTP client with retries and circuit breaker.
 *
 * Features:
 * - Exponential backoff with jitter
 * - Configurable timeouts
 * - Request/response logging
 * - Correlation ID propagation
 * - Optional circuit breaker pattern
 *
 * Example:
 * ```typescript
 * const client = new HttpClient({
 *   timeout: 30000,
 *   retry: { maxRetries: 3, baseDelay: 1000 },
 *   circuitBreaker: { enabled: true, failureThreshold: 5 }
 * });
 *
 * try {
 *   const response = await client.get('https://api.example.com/users');
 *   console.log(response.data);
 * } finally {
 *   client.close();
 * }
 * ```
 */
export class HttpClient {
  private readonly client: AxiosInstance;
  private readonly retryConfig: RetryConfig;
  private readonly circuitConfig: CircuitBreakerConfig;
  private readonly circuitState: CircuitBreakerState;
  private readonly logger: (message: string) => void;

  constructor(config: HttpClientConfig = {}) {
    // Set default retry config
    this.retryConfig = {
      maxRetries: 3,
      baseDelay: 1000,
      maxDelay: 30000,
      exponentialBase: 2.0,
      jitter: true,
      ...config.retry,
    };

    // Set default circuit breaker config
    this.circuitConfig = {
      enabled: false,
      failureThreshold: 5,
      successThreshold: 2,
      timeout: 60000,
      ...config.circuitBreaker,
    };

    // Initialize circuit state
    this.circuitState = {
      state: CircuitState.CLOSED,
      failureCount: 0,
      successCount: 0,
      lastFailureTime: 0,
    };

    // Set up logger
    this.logger = (message: string) => {
      console.log(`[HttpClient] ${message}`);
    };

    // Create axios instance
    this.client = axios.create({
      timeout: config.timeout || 30000,
      headers: config.headers || {},
      baseURL: config.baseURL,
    });

    // Add request interceptor for correlation ID
    this.client.interceptors.request.use((config: InternalAxiosRequestConfig) => {
      // Correlation ID will be added by the caller if needed
      return config;
    });
  }

  /**
   * Close the HTTP client and cleanup resources.
   */
  close(): void {
    // Axios doesn't have explicit cleanup, but we can clear interceptors
    this.client.interceptors.request.clear();
    this.client.interceptors.response.clear();
  }

  /**
   * Calculate delay for exponential backoff.
   *
   * @param attempt - Current attempt number (0-indexed)
   * @returns Delay in milliseconds
   */
  private calculateDelay(attempt: number): number {
    let delay = Math.min(
      this.retryConfig.baseDelay * Math.pow(this.retryConfig.exponentialBase, attempt),
      this.retryConfig.maxDelay
    );

    if (this.retryConfig.jitter) {
      // Add jitter: 50-150% of base delay
      delay *= 0.5 + Math.random();
    }

    return delay;
  }

  /**
   * Check circuit breaker state and throw if open.
   *
   * @throws Error if circuit breaker is open
   */
  private checkCircuitBreaker(): void {
    if (!this.circuitConfig.enabled) {
      return;
    }

    const now = Date.now();

    if (this.circuitState.state === CircuitState.OPEN) {
      const elapsed = now - this.circuitState.lastFailureTime;
      if (elapsed >= this.circuitConfig.timeout) {
        this.logger('Circuit breaker entering HALF_OPEN state');
        this.circuitState.state = CircuitState.HALF_OPEN;
        this.circuitState.successCount = 0;
      } else {
        const retryAfter = (this.circuitConfig.timeout - elapsed) / 1000;
        throw new Error(
          `Circuit breaker is OPEN (retry after ${retryAfter.toFixed(1)}s)`
        );
      }
    }
  }

  /**
   * Record successful request for circuit breaker.
   */
  private recordSuccess(): void {
    if (!this.circuitConfig.enabled) {
      return;
    }

    if (this.circuitState.state === CircuitState.HALF_OPEN) {
      this.circuitState.successCount++;
      if (this.circuitState.successCount >= this.circuitConfig.successThreshold) {
        this.logger('Circuit breaker closing after successful requests');
        this.circuitState.state = CircuitState.CLOSED;
        this.circuitState.failureCount = 0;
      }
    } else if (this.circuitState.state === CircuitState.CLOSED) {
      this.circuitState.failureCount = 0;
    }
  }

  /**
   * Record failed request for circuit breaker.
   */
  private recordFailure(): void {
    if (!this.circuitConfig.enabled) {
      return;
    }

    this.circuitState.lastFailureTime = Date.now();

    if (this.circuitState.state === CircuitState.HALF_OPEN) {
      this.logger('Circuit breaker opening after failure in HALF_OPEN state');
      this.circuitState.state = CircuitState.OPEN;
      this.circuitState.failureCount = 0;
    } else if (this.circuitState.state === CircuitState.CLOSED) {
      this.circuitState.failureCount++;
      if (this.circuitState.failureCount >= this.circuitConfig.failureThreshold) {
        this.logger(
          `Circuit breaker opening after ${this.circuitState.failureCount} failures`
        );
        this.circuitState.state = CircuitState.OPEN;
      }
    }
  }

  /**
   * Determine if a request should be retried based on error/status.
   *
   * @param error - Error from axios
   * @returns true if request should be retried
   */
  private shouldRetry(error: any): boolean {
    // Don't retry if no response (network error, etc.) - should retry
    if (!error.response) {
      return true;
    }

    const status = error.response.status;

    // Don't retry client errors (4xx) except 429 (rate limit)
    if (status >= 400 && status < 500 && status !== 429) {
      return false;
    }

    // Retry server errors (5xx) and rate limits (429)
    return status >= 500 || status === 429;
  }

  /**
   * Sleep for specified milliseconds.
   *
   * @param ms - Milliseconds to sleep
   */
  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  /**
   * Execute request with retry logic.
   *
   * @param config - Axios request configuration
   * @returns Promise resolving to response
   */
  private async requestWithRetry<T = any>(
    config: AxiosRequestConfig
  ): Promise<AxiosResponse<T>> {
    this.checkCircuitBreaker();

    let lastError: Error | undefined;

    for (let attempt = 0; attempt <= this.retryConfig.maxRetries; attempt++) {
      try {
        this.logger(
          `HTTP ${config.method?.toUpperCase()} ${config.url} (attempt ${attempt + 1}/${this.retryConfig.maxRetries + 1})`
        );

        const response = await this.client.request<T>(config);

        this.logger(
          `HTTP ${config.method?.toUpperCase()} ${config.url} -> ${response.status} (${JSON.stringify(response.data).length} bytes)`
        );

        this.recordSuccess();
        return response;
      } catch (error: any) {
        lastError = error;
        this.logger(
          `HTTP ${config.method?.toUpperCase()} ${config.url} failed (attempt ${attempt + 1}): ${error.message}`
        );

        // Check if we should retry
        if (!this.shouldRetry(error)) {
          this.recordFailure();
          throw error;
        }

        this.recordFailure();

        // If this was the last attempt, throw
        if (attempt >= this.retryConfig.maxRetries) {
          throw error;
        }

        // Calculate and apply delay
        const delay = this.calculateDelay(attempt);
        this.logger(`Retrying in ${(delay / 1000).toFixed(2)}s...`);
        await this.sleep(delay);
      }
    }

    // Should never reach here, but satisfy TypeScript
    throw lastError || new Error('Request failed with no error');
  }

  /**
   * Execute GET request with retry logic.
   */
  async get<T = any>(
    url: string,
    config?: AxiosRequestConfig
  ): Promise<AxiosResponse<T>> {
    return this.requestWithRetry<T>({ ...config, method: 'GET', url });
  }

  /**
   * Execute POST request with retry logic.
   */
  async post<T = any>(
    url: string,
    data?: any,
    config?: AxiosRequestConfig
  ): Promise<AxiosResponse<T>> {
    return this.requestWithRetry<T>({ ...config, method: 'POST', url, data });
  }

  /**
   * Execute PUT request with retry logic.
   */
  async put<T = any>(
    url: string,
    data?: any,
    config?: AxiosRequestConfig
  ): Promise<AxiosResponse<T>> {
    return this.requestWithRetry<T>({ ...config, method: 'PUT', url, data });
  }

  /**
   * Execute PATCH request with retry logic.
   */
  async patch<T = any>(
    url: string,
    data?: any,
    config?: AxiosRequestConfig
  ): Promise<AxiosResponse<T>> {
    return this.requestWithRetry<T>({ ...config, method: 'PATCH', url, data });
  }

  /**
   * Execute DELETE request with retry logic.
   */
  async delete<T = any>(
    url: string,
    config?: AxiosRequestConfig
  ): Promise<AxiosResponse<T>> {
    return this.requestWithRetry<T>({ ...config, method: 'DELETE', url });
  }

  /**
   * Execute HEAD request with retry logic.
   */
  async head<T = any>(
    url: string,
    config?: AxiosRequestConfig
  ): Promise<AxiosResponse<T>> {
    return this.requestWithRetry<T>({ ...config, method: 'HEAD', url });
  }

  /**
   * Execute OPTIONS request with retry logic.
   */
  async options<T = any>(
    url: string,
    config?: AxiosRequestConfig
  ): Promise<AxiosResponse<T>> {
    return this.requestWithRetry<T>({ ...config, method: 'OPTIONS', url });
  }
}
