/**
 * Audit logging for security events and compliance
 * Tracks security-relevant actions for investigation and compliance
 */

import { Request } from 'express';
import * as fs from 'fs';
import * as path from 'path';

/**
 * Audit event severity levels
 */
export enum AuditLevel {
  INFO = 'INFO',
  WARNING = 'WARNING',
  CRITICAL = 'CRITICAL',
}

/**
 * Audit event categories
 */
export enum AuditCategory {
  AUTHENTICATION = 'AUTHENTICATION',
  AUTHORIZATION = 'AUTHORIZATION',
  DATA_ACCESS = 'DATA_ACCESS',
  DATA_MODIFICATION = 'DATA_MODIFICATION',
  CONFIGURATION_CHANGE = 'CONFIGURATION_CHANGE',
  SECURITY_EVENT = 'SECURITY_EVENT',
  USER_MANAGEMENT = 'USER_MANAGEMENT',
  SYSTEM_EVENT = 'SYSTEM_EVENT',
}

/**
 * Audit event interface
 */
export interface AuditEvent {
  timestamp: string;
  level: AuditLevel;
  category: AuditCategory;
  action: string;
  userId?: string;
  userName?: string;
  ipAddress?: string;
  userAgent?: string;
  resource?: string;
  details?: Record<string, any>;
  success: boolean;
  errorMessage?: string;
  requestId?: string;
  sessionId?: string;
}

/**
 * Audit logger configuration
 */
export interface AuditLoggerOptions {
  /**
   * File path for audit log (optional, logs to console if not provided)
   */
  logFilePath?: string;

  /**
   * Enable console logging in addition to file
   */
  consoleOutput?: boolean;

  /**
   * Minimum level to log
   */
  minLevel?: AuditLevel;

  /**
   * Maximum log file size in bytes (triggers rotation)
   */
  maxFileSize?: number;

  /**
   * Number of rotated files to keep
   */
  maxFiles?: number;

  /**
   * Custom formatter for log entries
   */
  formatter?: (event: AuditEvent) => string;

  /**
   * Additional metadata to include in all events
   */
  defaultMetadata?: Record<string, any>;
}

/**
 * Default formatter for audit events
 */
function defaultFormatter(event: AuditEvent): string {
  return JSON.stringify(event);
}

/**
 * Audit logger class for security event logging
 */
export class AuditLogger {
  private options: Required<AuditLoggerOptions>;
  private writeStream?: fs.WriteStream;
  private currentFileSize: number = 0;

  constructor(options: AuditLoggerOptions = {}) {
    this.options = {
      logFilePath: options.logFilePath ?? '',
      consoleOutput: options.consoleOutput ?? true,
      minLevel: options.minLevel ?? AuditLevel.INFO,
      maxFileSize: options.maxFileSize ?? 100 * 1024 * 1024, // 100MB
      maxFiles: options.maxFiles ?? 10,
      formatter: options.formatter ?? defaultFormatter,
      defaultMetadata: options.defaultMetadata ?? {},
    };

    // Initialize file logging if path provided
    if (this.options.logFilePath) {
      this.initFileLogging();
    }
  }

  /**
   * Initialize file logging with rotation support
   */
  private initFileLogging(): void {
    const logDir = path.dirname(this.options.logFilePath);

    // Create directory if it doesn't exist
    if (!fs.existsSync(logDir)) {
      fs.mkdirSync(logDir, { recursive: true });
    }

    // Get current file size if exists
    if (fs.existsSync(this.options.logFilePath)) {
      const stats = fs.statSync(this.options.logFilePath);
      this.currentFileSize = stats.size;
    }

    // Create write stream
    this.writeStream = fs.createWriteStream(this.options.logFilePath, { flags: 'a' });
  }

  /**
   * Rotate log files
   */
  private rotateLog(): void {
    if (!this.options.logFilePath) return;

    // Close current stream
    this.writeStream?.end();

    // Rotate files
    for (let i = this.options.maxFiles - 1; i >= 0; i--) {
      const oldPath =
        i === 0 ? this.options.logFilePath : `${this.options.logFilePath}.${i}`;
      const newPath = `${this.options.logFilePath}.${i + 1}`;

      if (fs.existsSync(oldPath)) {
        if (i === this.options.maxFiles - 1) {
          fs.unlinkSync(oldPath); // Delete oldest
        } else {
          fs.renameSync(oldPath, newPath);
        }
      }
    }

    // Reset current file
    this.currentFileSize = 0;
    this.writeStream = fs.createWriteStream(this.options.logFilePath, { flags: 'a' });
  }

  /**
   * Check if event should be logged based on level
   */
  private shouldLog(level: AuditLevel): boolean {
    const levels = [AuditLevel.INFO, AuditLevel.WARNING, AuditLevel.CRITICAL];
    const eventLevelIndex = levels.indexOf(level);
    const minLevelIndex = levels.indexOf(this.options.minLevel);
    return eventLevelIndex >= minLevelIndex;
  }

  /**
   * Write log entry
   */
  private writeLog(event: AuditEvent): void {
    const logEntry = this.options.formatter(event) + '\n';

    // Console output
    if (this.options.consoleOutput) {
      console.log(logEntry.trim());
    }

    // File output
    if (this.writeStream) {
      this.writeStream.write(logEntry);
      this.currentFileSize += Buffer.byteLength(logEntry);

      // Check if rotation needed
      if (this.currentFileSize >= this.options.maxFileSize) {
        this.rotateLog();
      }
    }
  }

  /**
   * Log an audit event
   */
  public log(
    level: AuditLevel,
    category: AuditCategory,
    action: string,
    details: Partial<AuditEvent> = {}
  ): void {
    if (!this.shouldLog(level)) {
      return;
    }

    const event: AuditEvent = {
      timestamp: new Date().toISOString(),
      level,
      category,
      action,
      success: details.success ?? true,
      ...this.options.defaultMetadata,
      ...details,
    };

    this.writeLog(event);
  }

  /**
   * Log authentication event
   */
  public logAuth(action: string, success: boolean, details: Partial<AuditEvent> = {}): void {
    this.log(
      success ? AuditLevel.INFO : AuditLevel.WARNING,
      AuditCategory.AUTHENTICATION,
      action,
      { success, ...details }
    );
  }

  /**
   * Log authorization event
   */
  public logAuthz(action: string, success: boolean, details: Partial<AuditEvent> = {}): void {
    this.log(
      success ? AuditLevel.INFO : AuditLevel.WARNING,
      AuditCategory.AUTHORIZATION,
      action,
      { success, ...details }
    );
  }

  /**
   * Log data access event
   */
  public logDataAccess(resource: string, details: Partial<AuditEvent> = {}): void {
    this.log(AuditLevel.INFO, AuditCategory.DATA_ACCESS, 'data_access', {
      resource,
      ...details,
    });
  }

  /**
   * Log data modification event
   */
  public logDataModification(
    resource: string,
    action: string,
    details: Partial<AuditEvent> = {}
  ): void {
    this.log(AuditLevel.INFO, AuditCategory.DATA_MODIFICATION, action, {
      resource,
      ...details,
    });
  }

  /**
   * Log security event (high priority)
   */
  public logSecurityEvent(action: string, details: Partial<AuditEvent> = {}): void {
    this.log(AuditLevel.CRITICAL, AuditCategory.SECURITY_EVENT, action, details);
  }

  /**
   * Extract user info from Express request
   */
  public extractRequestInfo(req: Request): Partial<AuditEvent> {
    return {
      userId: (req as any).user?.id,
      userName: (req as any).user?.email || (req as any).user?.username,
      ipAddress: this.getClientIp(req),
      userAgent: req.headers['user-agent'],
      requestId: (req as any).id || req.headers['x-request-id'] as string,
      sessionId: (req as any).sessionID,
    };
  }

  /**
   * Get client IP address from request
   */
  private getClientIp(req: Request): string {
    const forwarded = req.headers['x-forwarded-for'];
    if (forwarded) {
      const ips = (forwarded as string).split(',');
      return ips[0].trim();
    }
    return req.ip || req.socket.remoteAddress || 'unknown';
  }

  /**
   * Create Express middleware for automatic request logging
   */
  public middleware() {
    return (req: Request, res: any, next: any): void => {
      const startTime = Date.now();

      // Log on response finish
      res.on('finish', () => {
        const duration = Date.now() - startTime;
        const success = res.statusCode < 400;

        this.log(
          success ? AuditLevel.INFO : AuditLevel.WARNING,
          AuditCategory.SYSTEM_EVENT,
          'http_request',
          {
            ...this.extractRequestInfo(req),
            success,
            resource: `${req.method} ${req.path}`,
            details: {
              statusCode: res.statusCode,
              duration,
              method: req.method,
              path: req.path,
            },
          }
        );
      });

      next();
    };
  }

  /**
   * Close audit logger and cleanup resources
   */
  public close(): void {
    if (this.writeStream) {
      this.writeStream.end();
    }
  }
}

/**
 * Create audit logger instance
 */
export function createAuditLogger(options?: AuditLoggerOptions): AuditLogger {
  return new AuditLogger(options);
}
