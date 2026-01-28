import React, { useEffect, useRef, useCallback, useState } from 'react';
import type { CaptchaWidgetProps, LoginColorConfig } from '../types';
import { ELDER_LOGIN_THEME } from '../themes/elderTheme';

// ALTCHA Web Component events
interface AltchaVerifiedEvent extends CustomEvent {
  detail: { payload: string };
}

interface AltchaErrorEvent extends CustomEvent {
  detail: { error: string };
}

/**
 * Logger utility for CAPTCHA widget - never logs tokens
 */
const log = {
  debug: (message: string, data?: Record<string, unknown>) => {
    if (process.env.NODE_ENV === 'development') {
      console.debug(`[LoginPage:CAPTCHA] ${message}`, data ?? '');
    }
  },
  info: (message: string, data?: Record<string, unknown>) => {
    console.info(`[LoginPage:CAPTCHA] ${message}`, data ?? '');
  },
  error: (message: string, error?: unknown) => {
    console.error(`[LoginPage:CAPTCHA] ${message}`, error instanceof Error ? error.message : error);
  },
};

/**
 * ALTCHA CAPTCHA widget wrapper.
 *
 * Features:
 * - Dynamic script loading for ALTCHA Web Component
 * - Proof-of-work verification
 * - Event handling for verified/error states
 * - Elder-styled container
 *
 * Requirements:
 * - Backend must expose challenge endpoint at `challengeUrl`
 * - Returns challenge data in ALTCHA format
 */
export const CaptchaWidget: React.FC<CaptchaWidgetProps> = ({
  challengeUrl,
  onVerified,
  onError,
  colors,
}) => {
  const theme: LoginColorConfig = { ...ELDER_LOGIN_THEME, ...colors };
  const containerRef = useRef<HTMLDivElement>(null);
  const widgetRef = useRef<HTMLElement | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Load ALTCHA script dynamically
  useEffect(() => {
    const SCRIPT_ID = 'altcha-script';
    const SCRIPT_URL = 'https://cdn.jsdelivr.net/npm/altcha/dist/altcha.min.js';

    const loadScript = async () => {
      // Check if script already exists
      if (document.getElementById(SCRIPT_ID)) {
        log.debug('ALTCHA script already loaded');
        setIsLoading(false);
        return;
      }

      log.debug('Loading ALTCHA script');

      try {
        const script = document.createElement('script');
        script.id = SCRIPT_ID;
        script.src = SCRIPT_URL;
        script.async = true;
        script.type = 'module';

        const loadPromise = new Promise<void>((resolve, reject) => {
          script.onload = () => {
            log.info('ALTCHA script loaded successfully');
            resolve();
          };
          script.onerror = () => {
            log.error('Failed to load ALTCHA script');
            reject(new Error('Failed to load CAPTCHA script'));
          };
        });

        document.head.appendChild(script);
        await loadPromise;
        setIsLoading(false);
      } catch (error) {
        setLoadError('Failed to load CAPTCHA. Please refresh the page.');
        setIsLoading(false);
        onError?.(error instanceof Error ? error : new Error('Script load failed'));
      }
    };

    loadScript();
  }, [onError]);

  // Create and configure ALTCHA widget
  useEffect(() => {
    if (isLoading || loadError || !containerRef.current) return;

    // Clean up existing widget
    if (widgetRef.current) {
      widgetRef.current.remove();
    }

    log.debug('Creating ALTCHA widget', { challengeUrl });

    // Create altcha-widget element
    const widget = document.createElement('altcha-widget');
    widget.setAttribute('challengeurl', challengeUrl);
    widget.setAttribute('auto', 'onload');

    // Apply theme styling via CSS custom properties
    widget.style.setProperty('--altcha-color-text', '#fbbf24'); // amber-400
    widget.style.setProperty('--altcha-color-border', '#475569'); // slate-600
    widget.style.setProperty('--altcha-color-border-focus', '#f59e0b'); // amber-500
    widget.style.setProperty('--altcha-max-width', '100%');

    widgetRef.current = widget;
    containerRef.current.appendChild(widget);

    // Event handlers
    const handleVerified = (e: Event) => {
      const event = e as AltchaVerifiedEvent;
      log.info('CAPTCHA verified successfully');
      onVerified(event.detail.payload);
    };

    const handleError = (e: Event) => {
      const event = e as AltchaErrorEvent;
      log.error('CAPTCHA verification failed', event.detail.error);
      onError?.(new Error(event.detail.error || 'CAPTCHA verification failed'));
    };

    widget.addEventListener('verified', handleVerified);
    widget.addEventListener('error', handleError);

    return () => {
      widget.removeEventListener('verified', handleVerified);
      widget.removeEventListener('error', handleError);
    };
  }, [isLoading, loadError, challengeUrl, onVerified, onError]);

  const handleRetry = useCallback(() => {
    log.debug('Retrying CAPTCHA widget load');
    setLoadError(null);
    setIsLoading(true);

    // Remove old script and try again
    const oldScript = document.getElementById('altcha-script');
    if (oldScript) {
      oldScript.remove();
    }
  }, []);

  return (
    <div className={`w-full rounded-lg border ${theme.cardBorder} ${theme.cardBackground} p-4`}>
      {isLoading && (
        <div className="flex items-center justify-center py-4">
          <svg
            className="animate-spin h-6 w-6 text-amber-400"
            fill="none"
            viewBox="0 0 24 24"
          >
            <circle
              className="opacity-25"
              cx="12"
              cy="12"
              r="10"
              stroke="currentColor"
              strokeWidth="4"
            />
            <path
              className="opacity-75"
              fill="currentColor"
              d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
            />
          </svg>
          <span className={`ml-2 text-sm ${theme.subtitleText}`}>
            Loading security check...
          </span>
        </div>
      )}

      {loadError && (
        <div className="text-center py-4">
          <p className={`text-sm ${theme.errorText} mb-2`}>{loadError}</p>
          <button
            onClick={handleRetry}
            className={`text-sm ${theme.linkText} ${theme.linkHoverText} underline`}
          >
            Try again
          </button>
        </div>
      )}

      <div
        ref={containerRef}
        className={isLoading || loadError ? 'hidden' : ''}
        aria-label="Security verification"
      />

      <p className={`mt-2 text-xs text-center ${theme.subtitleText}`}>
        Please complete the security check to continue
      </p>
    </div>
  );
};
