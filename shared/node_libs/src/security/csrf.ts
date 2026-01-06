/**
 * CSRF (Cross-Site Request Forgery) protection middleware
 * Implements double-submit cookie pattern and synchronizer token pattern
 */

import { Request, Response, NextFunction } from 'express';
import * as crypto from 'crypto';

/**
 * CSRF protection options
 */
export interface CSRFOptions {
  /**
   * Cookie name for CSRF token
   */
  cookieName?: string;

  /**
   * Header name for CSRF token
   */
  headerName?: string;

  /**
   * Cookie options
   */
  cookie?: {
    httpOnly?: boolean;
    secure?: boolean;
    sameSite?: 'strict' | 'lax' | 'none';
    path?: string;
    maxAge?: number;
  };

  /**
   * Token length in bytes (will be hex encoded, so actual length is 2x)
   */
  tokenLength?: number;

  /**
   * Methods to protect (default: POST, PUT, DELETE, PATCH)
   */
  protectedMethods?: string[];

  /**
   * Skip CSRF check based on request
   */
  skip?: (req: Request) => boolean;

  /**
   * Error handler for invalid token
   */
  onInvalidToken?: (req: Request, res: Response) => void;
}

/**
 * Generate cryptographically secure random token
 */
function generateToken(length: number): string {
  return crypto.randomBytes(length).toString('hex');
}

/**
 * Default invalid token handler
 */
function defaultInvalidTokenHandler(req: Request, res: Response): void {
  res.status(403).json({
    error: 'Forbidden',
    message: 'Invalid or missing CSRF token',
  });
}

/**
 * CSRF protection middleware factory
 * @param options - CSRF configuration options
 * @returns Express middleware function
 */
export function csrfProtection(
  options: CSRFOptions = {}
): (req: Request, res: Response, next: NextFunction) => void {
  const config: Required<CSRFOptions> = {
    cookieName: options.cookieName ?? 'XSRF-TOKEN',
    headerName: options.headerName ?? 'X-XSRF-TOKEN',
    cookie: {
      httpOnly: options.cookie?.httpOnly ?? false, // False so client JS can read
      secure: options.cookie?.secure ?? true,
      sameSite: options.cookie?.sameSite ?? 'strict',
      path: options.cookie?.path ?? '/',
      maxAge: options.cookie?.maxAge ?? 86400000, // 24 hours
    },
    tokenLength: options.tokenLength ?? 32,
    protectedMethods: options.protectedMethods ?? ['POST', 'PUT', 'DELETE', 'PATCH'],
    skip: options.skip ?? (() => false),
    onInvalidToken: options.onInvalidToken ?? defaultInvalidTokenHandler,
  };

  return (req: Request, res: Response, next: NextFunction): void => {
    // Skip if configured
    if (config.skip(req)) {
      next();
      return;
    }

    const method = req.method.toUpperCase();

    // Get or generate token
    let token = req.cookies?.[config.cookieName];

    if (!token) {
      token = generateToken(config.tokenLength);

      // Set cookie with token
      res.cookie(config.cookieName, token, {
        httpOnly: config.cookie.httpOnly,
        secure: config.cookie.secure,
        sameSite: config.cookie.sameSite,
        path: config.cookie.path,
        maxAge: config.cookie.maxAge,
      });
    }

    // Attach token to request for template rendering
    (req as any).csrfToken = (): string => token;

    // Check token for protected methods
    if (config.protectedMethods.includes(method)) {
      // Get token from header or body
      const submittedToken =
        req.headers[config.headerName.toLowerCase()] ||
        req.body?._csrf ||
        req.query?._csrf;

      // Validate token
      if (!submittedToken || submittedToken !== token) {
        config.onInvalidToken(req, res);
        return;
      }
    }

    next();
  };
}

/**
 * Double-submit cookie CSRF protection
 * More stateless than synchronizer token pattern
 */
export function doubleSubmitCsrf(
  options: CSRFOptions = {}
): (req: Request, res: Response, next: NextFunction) => void {
  const config: Required<CSRFOptions> = {
    cookieName: options.cookieName ?? 'CSRF-TOKEN',
    headerName: options.headerName ?? 'X-CSRF-TOKEN',
    cookie: {
      httpOnly: options.cookie?.httpOnly ?? true,
      secure: options.cookie?.secure ?? true,
      sameSite: options.cookie?.sameSite ?? 'strict',
      path: options.cookie?.path ?? '/',
      maxAge: options.cookie?.maxAge ?? 86400000, // 24 hours
    },
    tokenLength: options.tokenLength ?? 32,
    protectedMethods: options.protectedMethods ?? ['POST', 'PUT', 'DELETE', 'PATCH'],
    skip: options.skip ?? (() => false),
    onInvalidToken: options.onInvalidToken ?? defaultInvalidTokenHandler,
  };

  return (req: Request, res: Response, next: NextFunction): void => {
    // Skip if configured
    if (config.skip(req)) {
      next();
      return;
    }

    const method = req.method.toUpperCase();

    // Generate token if not present
    let cookieToken = req.cookies?.[config.cookieName];

    if (!cookieToken) {
      cookieToken = generateToken(config.tokenLength);

      res.cookie(config.cookieName, cookieToken, {
        httpOnly: config.cookie.httpOnly,
        secure: config.cookie.secure,
        sameSite: config.cookie.sameSite,
        path: config.cookie.path,
        maxAge: config.cookie.maxAge,
      });
    }

    // Validate for protected methods
    if (config.protectedMethods.includes(method)) {
      const headerToken = req.headers[config.headerName.toLowerCase()] as string;

      // Use timing-safe comparison
      if (!headerToken || !timingSafeEqual(cookieToken, headerToken)) {
        config.onInvalidToken(req, res);
        return;
      }
    }

    next();
  };
}

/**
 * Timing-safe string comparison to prevent timing attacks
 */
function timingSafeEqual(a: string, b: string): boolean {
  if (a.length !== b.length) {
    return false;
  }

  const bufA = Buffer.from(a, 'utf8');
  const bufB = Buffer.from(b, 'utf8');

  return crypto.timingSafeEqual(bufA, bufB);
}

/**
 * Middleware to expose CSRF token to templates
 * Adds req.csrfToken() function
 */
export function csrfTokenMiddleware(
  cookieName: string = 'XSRF-TOKEN',
  tokenLength: number = 32
): (req: Request, res: Response, next: NextFunction) => void {
  return (req: Request, res: Response, next: NextFunction): void => {
    let token = req.cookies?.[cookieName];

    if (!token) {
      token = generateToken(tokenLength);
      res.cookie(cookieName, token, {
        httpOnly: false,
        secure: true,
        sameSite: 'strict',
        path: '/',
        maxAge: 86400000, // 24 hours
      });
    }

    // Add token getter to request
    (req as any).csrfToken = (): string => token;

    // Add token to response locals for template access
    res.locals.csrfToken = token;

    next();
  };
}
