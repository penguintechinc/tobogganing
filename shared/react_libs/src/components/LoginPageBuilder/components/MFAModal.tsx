import React, { useState, useCallback } from 'react';
import type { MFAModalProps, LoginColorConfig } from '../types';
import { ELDER_LOGIN_THEME } from '../themes/elderTheme';
import { MFAInput } from './MFAInput';

/**
 * Logger utility for MFA - never logs the actual code
 */
const log = {
  debug: (message: string, data?: Record<string, unknown>) => {
    if (process.env.NODE_ENV === 'development') {
      console.debug(`[LoginPage:MFA] ${message}`, data ?? '');
    }
  },
  info: (message: string, data?: Record<string, unknown>) => {
    console.info(`[LoginPage:MFA] ${message}`, data ?? '');
  },
};

/**
 * MFA verification modal.
 *
 * Features:
 * - Modal popup for 2FA code entry
 * - 6-digit TOTP code input (Google Authenticator style)
 * - Optional "Remember this device" checkbox
 * - Cancel returns to login form
 * - Elder-styled dark theme
 */
export const MFAModal: React.FC<MFAModalProps> = ({
  isOpen,
  onClose,
  onSubmit,
  codeLength = 6,
  allowRememberDevice = false,
  colors,
  isSubmitting = false,
  error,
}) => {
  const theme: LoginColorConfig = { ...ELDER_LOGIN_THEME, ...colors };
  const [code, setCode] = useState('');
  const [rememberDevice, setRememberDevice] = useState(false);

  const handleSubmit = useCallback(
    (submittedCode?: string) => {
      const finalCode = submittedCode || code;
      if (finalCode.length !== codeLength) {
        log.debug('MFA code incomplete', { length: finalCode.length, required: codeLength });
        return;
      }

      log.info('MFA code submitted', {
        codeLength: finalCode.length,
        rememberDevice,
      });

      onSubmit(finalCode, rememberDevice);
    },
    [code, codeLength, onSubmit, rememberDevice]
  );

  const handleCodeComplete = useCallback(
    (completedCode: string) => {
      log.debug('MFA code auto-complete triggered');
      handleSubmit(completedCode);
    },
    [handleSubmit]
  );

  const handleClose = useCallback(() => {
    log.debug('MFA modal cancelled');
    setCode('');
    setRememberDevice(false);
    onClose();
  }, [onClose]);

  const handleFormSubmit = useCallback(
    (e: React.FormEvent) => {
      e.preventDefault();
      handleSubmit();
    },
    [handleSubmit]
  );

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-50 overflow-y-auto"
      aria-labelledby="mfa-modal-title"
      role="dialog"
      aria-modal="true"
    >
      {/* Backdrop */}
      <div className="flex min-h-screen items-center justify-center p-4">
        <div
          className="fixed inset-0 bg-black/60 transition-opacity"
          aria-hidden="true"
          onClick={handleClose}
        />

        {/* Modal */}
        <div
          className={`relative w-full max-w-md transform rounded-xl ${theme.cardBackground} border ${theme.cardBorder} p-6 shadow-2xl transition-all`}
        >
          {/* Header */}
          <div className="text-center mb-6">
            {/* Lock icon */}
            <div className="mx-auto w-12 h-12 rounded-full bg-amber-500/10 flex items-center justify-center mb-4">
              <svg
                className="w-6 h-6 text-amber-400"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 15v2m-6 4h12a2 2 0 002-2v-6a2 2 0 00-2-2H6a2 2 0 00-2 2v6a2 2 0 002 2zm10-10V7a4 4 0 00-8 0v4h8z"
                />
              </svg>
            </div>

            <h2 id="mfa-modal-title" className={`text-xl font-semibold ${theme.titleText}`}>
              Two-Factor Authentication
            </h2>
            <p className={`mt-2 text-sm ${theme.subtitleText}`}>
              Enter the 6-digit code from your authenticator app
            </p>
          </div>

          {/* Form */}
          <form onSubmit={handleFormSubmit}>
            {/* Code input */}
            <div className="mb-6">
              <MFAInput
                length={codeLength}
                value={code}
                onChange={setCode}
                onComplete={handleCodeComplete}
                disabled={isSubmitting}
                error={!!error}
                colors={colors}
              />

              {/* Error message */}
              {error && (
                <p className={`mt-3 text-sm text-center ${theme.errorText}`}>
                  {error}
                </p>
              )}
            </div>

            {/* Remember device option */}
            {allowRememberDevice && (
              <div className="flex items-center justify-center mb-6">
                <input
                  id="remember-device"
                  type="checkbox"
                  checked={rememberDevice}
                  onChange={(e) => setRememberDevice(e.target.checked)}
                  disabled={isSubmitting}
                  className={`h-4 w-4 rounded border-slate-600 bg-slate-900 text-amber-500 focus:ring-amber-500 focus:ring-offset-slate-800`}
                />
                <label
                  htmlFor="remember-device"
                  className={`ml-2 text-sm ${theme.subtitleText}`}
                >
                  Remember this device for 30 days
                </label>
              </div>
            )}

            {/* Buttons */}
            <div className="flex flex-col sm:flex-row gap-3">
              <button
                type="submit"
                disabled={isSubmitting || code.length !== codeLength}
                className={`
                  flex-1 py-2.5 px-4 rounded-lg font-medium
                  ${theme.primaryButton} ${theme.primaryButtonText} ${theme.primaryButtonHover}
                  disabled:opacity-50 disabled:cursor-not-allowed
                  transition-colors duration-200
                `}
              >
                {isSubmitting ? (
                  <span className="flex items-center justify-center">
                    <svg
                      className="animate-spin -ml-1 mr-2 h-4 w-4"
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
                    Verifying...
                  </span>
                ) : (
                  'Verify'
                )}
              </button>

              <button
                type="button"
                onClick={handleClose}
                disabled={isSubmitting}
                className={`
                  flex-1 py-2.5 px-4 rounded-lg font-medium border
                  ${theme.secondaryButton} ${theme.secondaryButtonText} ${theme.secondaryButtonBorder}
                  ${theme.secondaryButtonHover}
                  disabled:opacity-50 disabled:cursor-not-allowed
                  transition-colors duration-200
                `}
              >
                Cancel
              </button>
            </div>
          </form>

          {/* Help text */}
          <p className={`mt-4 text-xs text-center ${theme.subtitleText}`}>
            Open your authenticator app (Google Authenticator, Authy, etc.)
            to get your verification code.
          </p>
        </div>
      </div>
    </div>
  );
};
