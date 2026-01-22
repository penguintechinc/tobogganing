/**
 * Secure HTTP headers middleware for Express
 * Implements security best practices for HTTP headers
 */

import { Request, Response, NextFunction } from 'express';

/**
 * Security headers configuration options
 */
export interface SecurityHeadersOptions {
  /**
   * Content Security Policy directives
   */
  contentSecurityPolicy?: {
    directives?: Record<string, string[]>;
    reportOnly?: boolean;
  };

  /**
   * Enable HSTS (HTTP Strict Transport Security)
   */
  hsts?: {
    maxAge?: number;
    includeSubDomains?: boolean;
    preload?: boolean;
  };

  /**
   * X-Frame-Options value
   */
  frameOptions?: 'DENY' | 'SAMEORIGIN' | string;

  /**
   * Enable nosniff for X-Content-Type-Options
   */
  noSniff?: boolean;

  /**
   * Referrer-Policy value
   */
  referrerPolicy?: string;

  /**
   * Enable X-XSS-Protection
   */
  xssProtection?: boolean;

  /**
   * Permissions-Policy directives
   */
  permissionsPolicy?: Record<string, string[]>;

  /**
   * Custom headers to add
   */
  customHeaders?: Record<string, string>;
}

/**
 * Default security headers configuration
 */
const DEFAULT_OPTIONS: SecurityHeadersOptions = {
  contentSecurityPolicy: {
    directives: {
      'default-src': ["'self'"],
      'script-src': ["'self'", "'unsafe-inline'"],
      'style-src': ["'self'", "'unsafe-inline'"],
      'img-src': ["'self'", 'data:', 'https:'],
      'font-src': ["'self'", 'data:'],
      'connect-src': ["'self'"],
      'frame-ancestors': ["'none'"],
      'base-uri': ["'self'"],
      'form-action': ["'self'"],
    },
    reportOnly: false,
  },
  hsts: {
    maxAge: 31536000, // 1 year
    includeSubDomains: true,
    preload: true,
  },
  frameOptions: 'DENY',
  noSniff: true,
  referrerPolicy: 'strict-origin-when-cross-origin',
  xssProtection: true,
  permissionsPolicy: {
    camera: ["'none'"],
    microphone: ["'none'"],
    geolocation: ["'none'"],
    payment: ["'none'"],
  },
};

/**
 * Build Content-Security-Policy header value
 */
function buildCSP(directives: Record<string, string[]>): string {
  return Object.entries(directives)
    .map(([key, values]) => `${key} ${values.join(' ')}`)
    .join('; ');
}

/**
 * Build Permissions-Policy header value
 */
function buildPermissionsPolicy(policy: Record<string, string[]>): string {
  return Object.entries(policy)
    .map(([key, values]) => `${key}=(${values.join(' ')})`)
    .join(', ');
}

/**
 * Express middleware to set secure HTTP headers
 * @param options - Security headers configuration
 * @returns Express middleware function
 */
export function secureHeaders(
  options: SecurityHeadersOptions = {}
): (req: Request, res: Response, next: NextFunction) => void {
  const config = {
    ...DEFAULT_OPTIONS,
    ...options,
    contentSecurityPolicy: {
      ...DEFAULT_OPTIONS.contentSecurityPolicy,
      ...options.contentSecurityPolicy,
      directives: {
        ...DEFAULT_OPTIONS.contentSecurityPolicy?.directives,
        ...options.contentSecurityPolicy?.directives,
      },
    },
    hsts: {
      ...DEFAULT_OPTIONS.hsts,
      ...options.hsts,
    },
    permissionsPolicy: {
      ...DEFAULT_OPTIONS.permissionsPolicy,
      ...options.permissionsPolicy,
    },
  };

  return (req: Request, res: Response, next: NextFunction): void => {
    // Content-Security-Policy
    if (config.contentSecurityPolicy?.directives) {
      const cspValue = buildCSP(config.contentSecurityPolicy.directives);
      const headerName = config.contentSecurityPolicy.reportOnly
        ? 'Content-Security-Policy-Report-Only'
        : 'Content-Security-Policy';
      res.setHeader(headerName, cspValue);
    }

    // HSTS (only on HTTPS)
    if (config.hsts && (req.secure || req.headers['x-forwarded-proto'] === 'https')) {
      let hstsValue = `max-age=${config.hsts.maxAge}`;
      if (config.hsts.includeSubDomains) {
        hstsValue += '; includeSubDomains';
      }
      if (config.hsts.preload) {
        hstsValue += '; preload';
      }
      res.setHeader('Strict-Transport-Security', hstsValue);
    }

    // X-Frame-Options
    if (config.frameOptions) {
      res.setHeader('X-Frame-Options', config.frameOptions);
    }

    // X-Content-Type-Options
    if (config.noSniff) {
      res.setHeader('X-Content-Type-Options', 'nosniff');
    }

    // Referrer-Policy
    if (config.referrerPolicy) {
      res.setHeader('Referrer-Policy', config.referrerPolicy);
    }

    // X-XSS-Protection (legacy, but still useful for older browsers)
    if (config.xssProtection) {
      res.setHeader('X-XSS-Protection', '1; mode=block');
    }

    // Permissions-Policy
    if (config.permissionsPolicy) {
      const permissionsValue = buildPermissionsPolicy(config.permissionsPolicy);
      res.setHeader('Permissions-Policy', permissionsValue);
    }

    // Remove X-Powered-By header
    res.removeHeader('X-Powered-By');

    // Custom headers
    if (config.customHeaders) {
      Object.entries(config.customHeaders).forEach(([key, value]) => {
        res.setHeader(key, value);
      });
    }

    next();
  };
}

/**
 * CORS middleware with security defaults
 * @param options - CORS configuration
 */
export interface CORSOptions {
  origin?: string | string[] | boolean;
  methods?: string[];
  allowedHeaders?: string[];
  exposedHeaders?: string[];
  credentials?: boolean;
  maxAge?: number;
}

export function secureCORS(
  options: CORSOptions = {}
): (req: Request, res: Response, next: NextFunction) => void {
  const config: Required<CORSOptions> = {
    origin: options.origin ?? false,
    methods: options.methods ?? ['GET', 'POST', 'PUT', 'DELETE', 'OPTIONS'],
    allowedHeaders: options.allowedHeaders ?? ['Content-Type', 'Authorization'],
    exposedHeaders: options.exposedHeaders ?? [],
    credentials: options.credentials ?? false,
    maxAge: options.maxAge ?? 86400, // 24 hours
  };

  return (req: Request, res: Response, next: NextFunction): void => {
    // Handle origin
    const requestOrigin = req.headers.origin;
    if (config.origin === true) {
      res.setHeader('Access-Control-Allow-Origin', requestOrigin || '*');
    } else if (typeof config.origin === 'string') {
      res.setHeader('Access-Control-Allow-Origin', config.origin);
    } else if (Array.isArray(config.origin) && requestOrigin) {
      if (config.origin.includes(requestOrigin)) {
        res.setHeader('Access-Control-Allow-Origin', requestOrigin);
      }
    }

    // Other CORS headers
    res.setHeader('Access-Control-Allow-Methods', config.methods.join(', '));
    res.setHeader('Access-Control-Allow-Headers', config.allowedHeaders.join(', '));

    if (config.exposedHeaders.length > 0) {
      res.setHeader('Access-Control-Expose-Headers', config.exposedHeaders.join(', '));
    }

    if (config.credentials) {
      res.setHeader('Access-Control-Allow-Credentials', 'true');
    }

    res.setHeader('Access-Control-Max-Age', String(config.maxAge));

    // Handle preflight
    if (req.method === 'OPTIONS') {
      res.status(204).end();
      return;
    }

    next();
  };
}
