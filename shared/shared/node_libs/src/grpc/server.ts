/**
 * gRPC server helpers with health checks and graceful shutdown.
 */

import * as grpc from '@grpc/grpc-js';
import * as protoLoader from '@grpc/proto-loader';
import { HealthImplementation } from 'grpc-health-check';

export interface ServerOptions {
  maxWorkers?: number;
  maxConcurrentRPCs?: number;
  enableReflection?: boolean;
  enableHealthCheck?: boolean;
  port?: number;
  maxConnectionIdle?: number; // milliseconds
  maxConnectionAge?: number; // milliseconds
  keepaliveTime?: number; // milliseconds
  keepaliveTimeout?: number; // milliseconds
  gracefulStopTimeout?: number; // milliseconds
}

const DEFAULT_OPTIONS: Required<ServerOptions> = {
  maxWorkers: 10,
  maxConcurrentRPCs: 100,
  enableReflection: true,
  enableHealthCheck: true,
  port: 50051,
  maxConnectionIdle: 300000, // 5 minutes
  maxConnectionAge: 600000, // 10 minutes
  keepaliveTime: 60000, // 1 minute
  keepaliveTimeout: 20000, // 20 seconds
  gracefulStopTimeout: 30000, // 30 seconds
};

/**
 * Create a gRPC server with standard configuration.
 *
 * @param interceptors - List of server interceptors for auth, logging, etc.
 * @param options - Server configuration options
 * @returns Configured gRPC server instance
 *
 * @example
 * ```typescript
 * import { createServer, authInterceptor } from '@shared/grpc';
 *
 * const server = createServer([authInterceptor()], {
 *   port: 50051,
 *   maxConcurrentRPCs: 100,
 * });
 *
 * // Add your services
 * server.addService(MyServiceDefinition, implementation);
 *
 * server.bindAsync(
 *   '0.0.0.0:50051',
 *   grpc.ServerCredentials.createInsecure(),
 *   (err, port) => {
 *     if (err) throw err;
 *     server.start();
 *     console.log(`Server listening on port ${port}`);
 *   }
 * );
 * ```
 */
export function createServer(
  interceptors: grpc.Interceptor[] = [],
  options: ServerOptions = {}
): grpc.Server {
  const opts = { ...DEFAULT_OPTIONS, ...options };

  // Server options
  const serverOptions: grpc.ChannelOptions = {
    'grpc.max_concurrent_streams': opts.maxConcurrentRPCs,
    'grpc.max_connection_idle_ms': opts.maxConnectionIdle,
    'grpc.max_connection_age_ms': opts.maxConnectionAge,
    'grpc.keepalive_time_ms': opts.keepaliveTime,
    'grpc.keepalive_timeout_ms': opts.keepaliveTimeout,
    'grpc.http2.max_pings_without_data': 0,
    'grpc.http2.min_time_between_pings_ms': 10000,
    'grpc.http2.min_ping_interval_without_data_ms': 5000,
  };

  // Create server with interceptors
  const server = new grpc.Server({
    ...serverOptions,
    interceptors,
  });

  // Register health check service
  if (opts.enableHealthCheck) {
    registerHealthCheck(server);
  }

  console.log('gRPC server created', {
    maxWorkers: opts.maxWorkers,
    maxConcurrentRPCs: opts.maxConcurrentRPCs,
    interceptors: interceptors.length,
  });

  return server;
}

/**
 * Register health check service on the server.
 *
 * @param server - gRPC server instance
 * @returns Health service implementation
 *
 * @example
 * ```typescript
 * const server = new grpc.Server();
 * const healthCheck = registerHealthCheck(server);
 * healthCheck.setStatus('myservice', 'SERVING');
 * ```
 */
export function registerHealthCheck(server: grpc.Server): HealthImplementation {
  const healthImpl = new HealthImplementation({});
  healthImpl.addToServer(server);

  // Set overall server health
  healthImpl.setStatus('', 'SERVING');

  console.log('Health check service registered');
  return healthImpl;
}

/**
 * Start server and handle graceful shutdown on SIGTERM/SIGINT.
 *
 * @param server - gRPC server instance
 * @param port - Port to listen on
 * @param gracePeriod - Seconds to wait for ongoing RPCs to complete
 *
 * @example
 * ```typescript
 * const server = createServer();
 * // Add your services
 * startServerWithGracefulShutdown(server, 50051);
 * ```
 */
export function startServerWithGracefulShutdown(
  server: grpc.Server,
  port: number = 50051,
  gracePeriod: number = 30000
): void {
  server.bindAsync(
    `0.0.0.0:${port}`,
    grpc.ServerCredentials.createInsecure(),
    (err, boundPort) => {
      if (err) {
        console.error(`Failed to bind server: ${err.message}`);
        throw err;
      }

      server.start();
      console.log(`gRPC server listening on port ${boundPort}`);
    }
  );

  // Setup graceful shutdown
  const handleShutdown = (signal: string) => {
    console.log(`Received signal ${signal}, initiating graceful shutdown`);

    const deadline = Date.now() + gracePeriod;
    server.tryShutdown((error) => {
      if (error) {
        console.error('Error during graceful shutdown:', error);
      } else {
        console.log('Server stopped gracefully');
      }
      process.exit(error ? 1 : 0);
    });

    // Force shutdown if grace period exceeded
    setTimeout(() => {
      console.log('Graceful stop timeout, forcing shutdown');
      server.forceShutdown();
      process.exit(1);
    }, gracePeriod).unref();
  };

  process.on('SIGTERM', () => handleShutdown('SIGTERM'));
  process.on('SIGINT', () => handleShutdown('SIGINT'));
}
