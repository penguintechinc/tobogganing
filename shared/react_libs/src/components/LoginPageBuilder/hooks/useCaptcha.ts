import { useState, useCallback, useEffect } from 'react';
import type { UseCaptchaReturn, CaptchaConfig } from '../types';

const STORAGE_KEY = 'login_failed_attempts';

interface StoredAttemptData {
  count: number;
  timestamp: number;
}

/**
 * Logger utility for CAPTCHA hook - sanitizes sensitive data
 */
const log = {
  debug: (message: string, data?: Record<string, unknown>) => {
    if (process.env.NODE_ENV === 'development') {
      console.debug(`[LoginPage:CAPTCHA] ${message}`, data ? sanitizeLogData(data) : '');
    }
  },
  info: (message: string, data?: Record<string, unknown>) => {
    console.info(`[LoginPage:CAPTCHA] ${message}`, data ? sanitizeLogData(data) : '');
  },
  warn: (message: string, data?: Record<string, unknown>) => {
    console.warn(`[LoginPage:CAPTCHA] ${message}`, data ? sanitizeLogData(data) : '');
  },
  error: (message: string, error?: unknown) => {
    console.error(`[LoginPage:CAPTCHA] ${message}`, error instanceof Error ? error.message : error);
  },
};

function sanitizeLogData(data: Record<string, unknown>): Record<string, unknown> {
  const sanitized = { ...data };
  // Never log tokens or sensitive data
  if ('token' in sanitized) sanitized.token = '[REDACTED]';
  if ('captchaToken' in sanitized) sanitized.captchaToken = sanitized.captchaToken ? '[SET]' : '[NOT_SET]';
  return sanitized;
}

/**
 * Hook for managing CAPTCHA state and failed login attempt tracking.
 *
 * Features:
 * - Tracks failed login attempts in localStorage
 * - Shows CAPTCHA after threshold is exceeded
 * - Auto-resets attempts after configurable timeout (default: 15 min)
 * - Provides verification state management
 */
export function useCaptcha(config?: CaptchaConfig): UseCaptchaReturn {
  const threshold = config?.failedAttemptsThreshold ?? 3;
  const resetTimeout = config?.resetTimeoutMs ?? 900000; // 15 minutes default
  const enabled = config?.enabled ?? false;

  const [failedAttempts, setFailedAttempts] = useState<number>(0);
  const [captchaToken, setCaptchaToken] = useState<string | null>(null);

  // Load stored attempts on mount
  useEffect(() => {
    if (!enabled) return;

    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const data: StoredAttemptData = JSON.parse(stored);
        const now = Date.now();

        // Check if attempts should be reset due to timeout
        if (now - data.timestamp > resetTimeout) {
          log.debug('Resetting expired failed attempts');
          localStorage.removeItem(STORAGE_KEY);
          setFailedAttempts(0);
        } else {
          log.debug('Loaded failed attempts from storage');
          setFailedAttempts(data.count);
        }
      }
    } catch (error) {
      log.error('Failed to load attempts from storage', error);
      localStorage.removeItem(STORAGE_KEY);
    }
  }, [enabled, resetTimeout]);

  const incrementFailedAttempts = useCallback(() => {
    if (!enabled) return;

    setFailedAttempts((prev) => {
      const newCount = prev + 1;
      const data: StoredAttemptData = {
        count: newCount,
        timestamp: Date.now(),
      };

      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(data));
        log.info('Failed login attempt recorded', {
          attemptNumber: newCount,
        });
      } catch (error) {
        log.error('Failed to store attempt count', error);
      }

      return newCount;
    });

    // Reset CAPTCHA token on new failed attempt
    setCaptchaToken(null);
  }, [enabled, threshold]);

  const resetFailedAttempts = useCallback(() => {
    if (!enabled) return;

    log.debug('Resetting failed attempts after successful action');
    setFailedAttempts(0);
    setCaptchaToken(null);
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch (error) {
      log.error('Failed to clear stored attempts', error);
    }
  }, [enabled]);

  const handleSetCaptchaToken = useCallback((token: string | null) => {
    log.debug('CAPTCHA token updated', { captchaToken: token });
    setCaptchaToken(token);
  }, []);

  const showCaptcha = enabled && failedAttempts >= threshold;
  const isVerified = enabled ? !!captchaToken : true;

  return {
    showCaptcha,
    failedAttempts,
    incrementFailedAttempts,
    resetFailedAttempts,
    captchaToken,
    setCaptchaToken: handleSetCaptchaToken,
    isVerified,
  };
}
