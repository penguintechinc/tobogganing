/**
 * gRPC client with connection management, retries, and TLS support.
 */

import * as grpc from '@grpc/grpc-js';
import * as fs from 'fs';

export interface ClientOptions {
  maxRetries?: number;
  initialBackoffMs?: number;
  maxBackoffMs?: number;
  backoffMultiplier?: number;
  timeoutSeconds?: number;
  enableTLS?: boolean;
  caCertPath?: string;
  clientCertPath?: string;
  clientKeyPath?: string;
  keepaliveTimeMs?: number;
  keepaliveTimeoutMs?: number;
}

const DEFAULT_OPTIONS: Required<ClientOptions> = {
  maxRetries: 3,
  initialBackoffMs: 100,
  maxBackoffMs: 5000,
  backoffMultiplier: 2.0,
  timeoutSeconds: 30,
  enableTLS: false,
  caCertPath: '',
  clientCertPath: '',
  clientKeyPath: '',
  keepaliveTimeMs: 60000, // 1 minute
  keepaliveTimeoutMs: 20000, // 20 seconds
};

/**
 * gRPC client wrapper with connection management and retry logic.
 *
 * @example
 * ```typescript
 * import { GrpcClient } from '@shared/grpc';
 * import { MyServiceClient } from './generated/myservice_grpc_pb';
 *
 * const client = new GrpcClient('localhost:50051', {
 *   enableTLS: true,
 *   maxRetries: 5,
 * });
 *
 * const stub = new MyServiceClient(
 *   client.target,
 *   client.credentials
 * );
 *
 * await client.callWithRetry(async () => {
 *   return new Promise((resolve, reject) => {
 *     stub.myMethod(request, (err, response) => {
 *       if (err) reject(err);
 *       else resolve(response);
 *     });
 *   });
 * });
 *
 * client.close();
 * ```
 */
export class GrpcClient {
  private options: Required<ClientOptions>;
  private _credentials: grpc.ChannelCredentials;

  constructor(public readonly target: string, options: ClientOptions = {}) {
    this.options = { ...DEFAULT_OPTIONS, ...options };
    this._credentials = this.createCredentials();

    console.log(`gRPC client initialized for ${target}`);
  }

  /**
   * Get gRPC channel credentials.
   */
  get credentials(): grpc.ChannelCredentials {
    return this._credentials;
  }

  /**
   * Create a gRPC channel with configuration.
   */
  createChannel(): grpc.Channel {
    const channelOptions: grpc.ChannelOptions = {
      'grpc.keepalive_time_ms': this.options.keepaliveTimeMs,
      'grpc.keepalive_timeout_ms': this.options.keepaliveTimeoutMs,
      'grpc.keepalive_permit_without_calls': 1,
      'grpc.http2.max_pings_without_data': 0,
    };

    const channel = grpc.createChannel(
      this.target,
      this._credentials,
      channelOptions
    );

    console.log(
      `${this.options.enableTLS ? 'Secure' : 'Insecure'} gRPC channel created to ${this.target}`
    );

    return channel;
  }

  /**
   * Create credentials for gRPC channel.
   */
  private createCredentials(): grpc.ChannelCredentials {
    if (!this.options.enableTLS) {
      return grpc.credentials.createInsecure();
    }

    let rootCerts: Buffer | null = null;
    if (this.options.caCertPath) {
      rootCerts = fs.readFileSync(this.options.caCertPath);
    }

    let privateKey: Buffer | null = null;
    let certChain: Buffer | null = null;
    if (this.options.clientCertPath && this.options.clientKeyPath) {
      privateKey = fs.readFileSync(this.options.clientKeyPath);
      certChain = fs.readFileSync(this.options.clientCertPath);
    }

    return grpc.credentials.createSsl(rootCerts, privateKey, certChain);
  }

  /**
   * Call gRPC method with exponential backoff retry.
   *
   * @param fn - Function that executes the gRPC call
   * @returns Response from the gRPC method
   * @throws Error if all retries fail
   *
   * @example
   * ```typescript
   * const response = await client.callWithRetry(async () => {
   *   return new Promise((resolve, reject) => {
   *     stub.myMethod(request, (err, response) => {
   *       if (err) reject(err);
   *       else resolve(response);
   *     });
   *   });
   * });
   * ```
   */
  async callWithRetry<T>(fn: () => Promise<T>): Promise<T> {
    let backoffMs = this.options.initialBackoffMs;
    let lastError: Error | undefined;

    for (let attempt = 0; attempt < this.options.maxRetries; attempt++) {
      try {
        return await fn();
      } catch (error) {
        lastError = error as Error;

        // Check if error is retryable
        if (!this.isRetryable(error)) {
          console.error('Non-retryable error:', error);
          throw error;
        }

        // Retry with exponential backoff
        if (attempt < this.options.maxRetries - 1) {
          console.warn(
            `RPC failed (attempt ${attempt + 1}/${this.options.maxRetries}), retrying in ${backoffMs}ms:`,
            error
          );

          await this.sleep(backoffMs);

          backoffMs = Math.min(
            backoffMs * this.options.backoffMultiplier,
            this.options.maxBackoffMs
          );
        } else {
          console.error(
            `RPC failed after ${this.options.maxRetries} attempts:`,
            error
          );
        }
      }
    }

    throw lastError || new Error('Unexpected error in callWithRetry');
  }

  /**
   * Check if a gRPC error should be retried.
   */
  private isRetryable(error: any): boolean {
    const code = error?.code;

    // Don't retry on these error codes
    const nonRetryableCodes = [
      grpc.status.INVALID_ARGUMENT,
      grpc.status.NOT_FOUND,
      grpc.status.ALREADY_EXISTS,
      grpc.status.PERMISSION_DENIED,
      grpc.status.UNAUTHENTICATED,
    ];

    return !nonRetryableCodes.includes(code);
  }

  /**
   * Sleep for the specified milliseconds.
   */
  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => setTimeout(resolve, ms));
  }

  /**
   * Close the gRPC channel (if needed for cleanup).
   */
  close(): void {
    console.log(`gRPC client to ${this.target} closed`);
  }
}
