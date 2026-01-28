import React, { useState, useCallback, useEffect } from 'react';
import type {
  LoginPageBuilderProps,
  LoginPayload,
  LoginResponse,
  LoginColorConfig,
  SocialLoginConfig,
  CookieConsentState,
} from './types';
import { mergeWithElderTheme } from './themes/elderTheme';
import { useCaptcha } from './hooks/useCaptcha';
import { useCookieConsent } from './hooks/useCookieConsent';
import { MFAModal } from './components/MFAModal';
import { CaptchaWidget } from './components/CaptchaWidget';
import { SocialLoginButtons, LoginDivider } from './components/SocialLoginButtons';
import { CookieConsent } from './components/CookieConsent';
import { Footer } from './components/Footer';
import { buildOAuth2Url, buildCustomOAuth2Url, buildOIDCUrl } from './utils/oauth';
import { initiateSAMLLogin } from './utils/saml';

/**
 * Logger utility - sanitizes all sensitive data before logging
 */
const log = {
  debug: (message: string, data?: Record<string, unknown>) => {
    if (process.env.NODE_ENV === 'development') {
      console.debug(`[LoginPage] ${message}`, data ? sanitizeLogData(data) : '');
    }
  },
  info: (message: string, data?: Record<string, unknown>) => {
    console.info(`[LoginPage] ${message}`, data ? sanitizeLogData(data) : '');
  },
  warn: (message: string, data?: Record<string, unknown>) => {
    console.warn(`[LoginPage] ${message}`, data ? sanitizeLogData(data) : '');
  },
  error: (message: string, error?: unknown) => {
    // For errors, only log the message, never stack traces with sensitive context
    const errorMessage = error instanceof Error ? error.message : String(error);
    console.error(`[LoginPage] ${message}`, errorMessage);
  },
};

function sanitizeLogData(data: Record<string, unknown>): Record<string, unknown> {
  const sanitized = { ...data };
  // Never log sensitive authentication data
  const sensitiveKeys = [
    'password', 'token', 'accessToken', 'refreshToken', 'mfaCode',
    'captchaToken', 'email', 'code', 'secret', 'credential'
  ];
  for (const key of sensitiveKeys) {
    if (key in sanitized) {
      sanitized[key] = '[REDACTED]';
    }
  }
  // Show email domain only for troubleshooting
  if (typeof sanitized.emailDomain === 'string') {
    sanitized.emailDomain = sanitized.emailDomain;
  }
  return sanitized;
}

/**
 * LoginPageBuilder - A comprehensive, configurable login page component.
 *
 * Features:
 * - Elder-style dark theme with gold/amber accents
 * - ALTCHA proof-of-work CAPTCHA (triggers after failed attempts)
 * - MFA/2FA support with 6-digit TOTP input
 * - Social login support (OAuth2, OIDC, SAML)
 * - GDPR cookie consent banner
 * - Full theming customization
 */
export const LoginPageBuilder: React.FC<LoginPageBuilderProps> = ({
  api,
  branding,
  onSuccess,
  gdpr,
  captcha,
  mfa,
  colors,
  showForgotPassword = true,
  forgotPasswordUrl,
  onForgotPassword,
  showSignUp = true,
  signUpUrl,
  onSignUp,
  showRememberMe = true,
  className,
  socialLogins,
  onError,
  transformErrorMessage,
}) => {
  const theme: LoginColorConfig = mergeWithElderTheme(colors);

  // Form state
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [rememberMe, setRememberMe] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // MFA state
  const [showMFA, setShowMFA] = useState(false);
  const [mfaError, setMfaError] = useState<string | null>(null);
  // Store pending response for MFA flow (used when MFA modal shows)
  const [, setPendingLoginResponse] = useState<LoginResponse | null>(null);

  // CAPTCHA hook
  const {
    showCaptcha,
    incrementFailedAttempts,
    resetFailedAttempts,
    captchaToken,
    setCaptchaToken,
    isVerified: captchaVerified,
  } = useCaptcha(captcha);

  // Cookie consent hook
  const {
    showBanner,
    canInteract,
    acceptAll,
    acceptEssential,
    savePreferences,
  } = useCookieConsent(gdpr);

  // Log component mount
  useEffect(() => {
    log.info('LoginPage mounted', {
      appName: branding.appName,
      captchaEnabled: captcha?.enabled ?? false,
      mfaEnabled: mfa?.enabled ?? false,
      socialProviders: socialLogins?.length ?? 0,
      gdprEnabled: gdpr?.enabled ?? true,
    });
  }, [branding.appName, captcha?.enabled, mfa?.enabled, socialLogins?.length, gdpr?.enabled]);

  /**
   * Handle form submission
   */
  const handleSubmit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();

      if (!canInteract) {
        log.warn('Login attempt blocked - cookie consent required');
        return;
      }

      // Validate CAPTCHA if required
      if (showCaptcha && !captchaVerified) {
        log.warn('Login attempt blocked - CAPTCHA not verified');
        setError('Please complete the security check');
        return;
      }

      setError(null);
      setIsSubmitting(true);

      // Extract email domain for logging (never log full email)
      const emailDomain = email.includes('@') ? email.split('@')[1] : 'unknown';

      log.info('Login attempt started', {
        emailDomain,
        rememberMe,
        hasCaptcha: !!captchaToken,
      });

      const payload: LoginPayload = {
        email,
        password,
        rememberMe,
        captchaToken: captchaToken ?? undefined,
      };

      try {
        const response = await fetch(api.loginUrl, {
          method: api.method || 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...api.headers,
          },
          body: JSON.stringify(payload),
        });

        const data: LoginResponse = await response.json();

        if (!response.ok || !data.success) {
          // Login failed
          incrementFailedAttempts();
          const errorMessage = transformErrorMessage
            ? transformErrorMessage(data.error || 'Login failed', data.errorCode)
            : data.error || 'Invalid email or password';

          log.warn('Login failed', {
            emailDomain,
            errorCode: data.errorCode,
            status: response.status,
          });

          setError(errorMessage);
          onError?.(new Error(errorMessage), data.errorCode);
          return;
        }

        // Check if MFA is required
        if (data.mfaRequired && mfa?.enabled) {
          log.info('MFA required for login', { emailDomain });
          setPendingLoginResponse(data);
          setShowMFA(true);
          return;
        }

        // Success!
        log.info('Login successful', { emailDomain });
        resetFailedAttempts();
        onSuccess(data);
      } catch (err) {
        incrementFailedAttempts();
        const errorMessage = transformErrorMessage
          ? transformErrorMessage('Network error', 'NETWORK_ERROR')
          : 'Unable to connect. Please check your connection and try again.';

        log.error('Login network error', err);
        setError(errorMessage);
        onError?.(err instanceof Error ? err : new Error(errorMessage), 'NETWORK_ERROR');
      } finally {
        setIsSubmitting(false);
      }
    },
    [
      email, password, rememberMe, canInteract, showCaptcha, captchaVerified,
      captchaToken, api, mfa?.enabled, incrementFailedAttempts, resetFailedAttempts,
      onSuccess, onError, transformErrorMessage,
    ]
  );

  /**
   * Handle MFA code submission
   */
  const handleMFASubmit = useCallback(
    async (code: string, rememberDevice?: boolean) => {
      setMfaError(null);
      setIsSubmitting(true);

      log.info('MFA verification started', { rememberDevice });

      try {
        const payload: LoginPayload = {
          email,
          password,
          rememberMe,
          mfaCode: code,
        };

        const response = await fetch(api.loginUrl, {
          method: api.method || 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...api.headers,
          },
          body: JSON.stringify({
            ...payload,
            mfaCode: code,
            rememberDevice,
          }),
        });

        const data: LoginResponse = await response.json();

        if (!response.ok || !data.success) {
          const errorMessage = data.error || 'Invalid verification code';
          log.warn('MFA verification failed', { errorCode: data.errorCode });
          setMfaError(errorMessage);
          return;
        }

        // MFA Success!
        log.info('MFA verification successful');
        setShowMFA(false);
        resetFailedAttempts();
        onSuccess(data);
      } catch (err) {
        log.error('MFA verification network error', err);
        setMfaError('Unable to verify code. Please try again.');
      } finally {
        setIsSubmitting(false);
      }
    },
    [email, password, rememberMe, api, resetFailedAttempts, onSuccess]
  );

  /**
   * Handle MFA modal close
   */
  const handleMFAClose = useCallback(() => {
    log.debug('MFA modal closed by user');
    setShowMFA(false);
    setMfaError(null);
    setPendingLoginResponse(null);
  }, []);

  /**
   * Handle social login provider click
   */
  const handleSocialLogin = useCallback(
    async (config: SocialLoginConfig) => {
      if (!canInteract) {
        log.warn('Social login blocked - cookie consent required');
        return;
      }

      log.info('Social login initiated', { provider: config.provider });

      try {
        let authUrl: string;

        switch (config.provider) {
          case 'google':
          case 'github':
          case 'microsoft':
          case 'apple':
          case 'twitch':
          case 'discord':
            authUrl = buildOAuth2Url(config);
            break;

          case 'oauth2':
            authUrl = buildCustomOAuth2Url(config);
            break;

          case 'oidc':
            authUrl = await buildOIDCUrl(config);
            break;

          case 'saml':
            initiateSAMLLogin(config);
            return;

          default:
            log.error('Unknown social provider', { provider: (config as SocialLoginConfig).provider });
            return;
        }

        // Redirect to OAuth provider
        window.location.href = authUrl;
      } catch (err) {
        log.error('Social login failed', err);
        setError('Failed to initiate login. Please try again.');
      }
    },
    [canInteract]
  );

  /**
   * Handle CAPTCHA verification
   */
  const handleCaptchaVerified = useCallback(
    (token: string) => {
      log.info('CAPTCHA verified');
      setCaptchaToken(token);
    },
    [setCaptchaToken]
  );

  /**
   * Handle CAPTCHA error
   */
  const handleCaptchaError = useCallback((err: Error) => {
    log.error('CAPTCHA verification error', err);
    setError('Security check failed. Please try again.');
  }, []);

  /**
   * Handle cookie consent
   */
  const handleCookieAccept = useCallback(
    (consent: CookieConsentState) => {
      if (consent.functional && consent.analytics && consent.marketing) {
        acceptAll();
      } else if (!consent.functional && !consent.analytics && !consent.marketing) {
        acceptEssential();
      } else {
        savePreferences(consent);
      }
    },
    [acceptAll, acceptEssential, savePreferences]
  );

  /**
   * Handle forgot password click
   */
  const handleForgotPassword = useCallback(
    (e: React.MouseEvent) => {
      if (onForgotPassword) {
        e.preventDefault();
        log.debug('Forgot password clicked (callback)');
        onForgotPassword();
      } else {
        log.debug('Forgot password clicked (navigation)');
      }
    },
    [onForgotPassword]
  );

  /**
   * Handle sign up click
   */
  const handleSignUp = useCallback(
    (e: React.MouseEvent) => {
      if (onSignUp) {
        e.preventDefault();
        log.debug('Sign up clicked (callback)');
        onSignUp();
      } else {
        log.debug('Sign up clicked (navigation)');
      }
    },
    [onSignUp]
  );

  // Render logo
  const renderLogo = () => {
    if (!branding.logo) return null;

    const logoWidth = branding.logoWidth ?? 300;

    if (typeof branding.logo === 'string') {
      return (
        <img
          src={branding.logo}
          alt={`${branding.appName} logo`}
          style={{ width: logoWidth, height: 'auto' }}
          className="mx-auto"
        />
      );
    }

    return <div style={{ width: logoWidth }} className="mx-auto">{branding.logo}</div>;
  };

  return (
    <div className={`min-h-screen ${theme.pageBackground} flex flex-col justify-center py-12 sm:px-6 lg:px-8 ${className || ''}`}>
      <div className="sm:mx-auto sm:w-full sm:max-w-md">
        {/* Logo */}
        {branding.logo && <div className="mb-6">{renderLogo()}</div>}

        {/* App name and tagline */}
        <h1 className={`text-center text-3xl font-bold ${theme.titleText}`}>
          {branding.appName}
        </h1>
        {branding.tagline && (
          <p className={`mt-2 text-center text-sm ${theme.subtitleText}`}>
            {branding.tagline}
          </p>
        )}
      </div>

      <div className="mt-8 sm:mx-auto sm:w-full sm:max-w-md">
        <div className={`${theme.cardBackground} border ${theme.cardBorder} py-8 px-4 shadow-xl sm:rounded-xl sm:px-10`}>
          {/* Error message */}
          {error && (
            <div className={`mb-4 p-3 rounded-lg bg-red-500/10 border border-red-500/30 ${theme.errorText}`}>
              <p className="text-sm">{error}</p>
            </div>
          )}

          {/* Social login buttons (above form) */}
          {socialLogins && socialLogins.length > 0 && (
            <>
              <SocialLoginButtons
                providers={socialLogins}
                onProviderClick={handleSocialLogin}
                colors={colors}
                disabled={!canInteract || isSubmitting}
              />
              <LoginDivider colors={colors} />
            </>
          )}

          {/* Login form */}
          <form onSubmit={handleSubmit} className="space-y-5">
            {/* Email field */}
            <div>
              <label htmlFor="email" className={`block text-sm font-medium ${theme.labelText}`}>
                Email address
              </label>
              <input
                id="email"
                name="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                disabled={!canInteract || isSubmitting}
                className={`
                  mt-1 block w-full rounded-lg border px-3 py-2.5
                  ${theme.inputBackground} ${theme.inputBorder} ${theme.inputText} ${theme.placeholderText}
                  ${theme.inputFocusBorder} ${theme.inputFocusRing}
                  focus:outline-none focus:ring-2
                  disabled:opacity-50 disabled:cursor-not-allowed
                  transition-colors duration-200
                `}
                placeholder="you@example.com"
              />
            </div>

            {/* Password field */}
            <div>
              <label htmlFor="password" className={`block text-sm font-medium ${theme.labelText}`}>
                Password
              </label>
              <input
                id="password"
                name="password"
                type="password"
                autoComplete="current-password"
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                disabled={!canInteract || isSubmitting}
                className={`
                  mt-1 block w-full rounded-lg border px-3 py-2.5
                  ${theme.inputBackground} ${theme.inputBorder} ${theme.inputText} ${theme.placeholderText}
                  ${theme.inputFocusBorder} ${theme.inputFocusRing}
                  focus:outline-none focus:ring-2
                  disabled:opacity-50 disabled:cursor-not-allowed
                  transition-colors duration-200
                `}
                placeholder="Enter your password"
              />
            </div>

            {/* Remember me / Forgot password row */}
            <div className="flex items-center justify-between">
              {showRememberMe && (
                <div className="flex items-center">
                  <input
                    id="remember-me"
                    name="remember-me"
                    type="checkbox"
                    checked={rememberMe}
                    onChange={(e) => setRememberMe(e.target.checked)}
                    disabled={!canInteract || isSubmitting}
                    className="h-4 w-4 rounded border-slate-600 bg-slate-900 text-amber-500 focus:ring-amber-500 focus:ring-offset-slate-800"
                  />
                  <label htmlFor="remember-me" className={`ml-2 block text-sm ${theme.subtitleText}`}>
                    Remember me
                  </label>
                </div>
              )}

              {showForgotPassword && (
                <a
                  href={forgotPasswordUrl || '#'}
                  onClick={handleForgotPassword}
                  className={`text-sm font-medium ${theme.linkText} ${theme.linkHoverText} transition-colors`}
                >
                  Forgot password?
                </a>
              )}
            </div>

            {/* CAPTCHA widget */}
            {showCaptcha && captcha && (
              <div className="mt-4">
                <CaptchaWidget
                  challengeUrl={captcha.challengeUrl}
                  onVerified={handleCaptchaVerified}
                  onError={handleCaptchaError}
                  colors={colors}
                />
              </div>
            )}

            {/* Submit button */}
            <button
              type="submit"
              disabled={!canInteract || isSubmitting || (showCaptcha && !captchaVerified)}
              className={`
                w-full flex justify-center py-2.5 px-4 rounded-lg font-medium
                ${theme.primaryButton} ${theme.primaryButtonText} ${theme.primaryButtonHover}
                disabled:opacity-50 disabled:cursor-not-allowed
                transition-colors duration-200
              `}
            >
              {isSubmitting ? (
                <span className="flex items-center">
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
                  Signing in...
                </span>
              ) : (
                'Sign in'
              )}
            </button>
          </form>

          {/* Sign up link */}
          {showSignUp && (
            <p className={`mt-6 text-center text-sm ${theme.subtitleText}`}>
              Don&apos;t have an account?{' '}
              <a
                href={signUpUrl || '#'}
                onClick={handleSignUp}
                className={`font-medium ${theme.linkText} ${theme.linkHoverText} transition-colors`}
              >
                Sign up
              </a>
            </p>
          )}
        </div>

        {/* Footer */}
        <Footer githubRepo={branding.githubRepo} colors={colors} />
      </div>

      {/* MFA Modal */}
      {mfa?.enabled && (
        <MFAModal
          isOpen={showMFA}
          onClose={handleMFAClose}
          onSubmit={handleMFASubmit}
          codeLength={mfa.codeLength ?? 6}
          allowRememberDevice={mfa.allowRememberDevice}
          colors={colors}
          isSubmitting={isSubmitting}
          error={mfaError ?? undefined}
        />
      )}

      {/* GDPR Cookie Consent Banner */}
      {gdpr && showBanner && (
        <CookieConsent
          gdpr={gdpr}
          onAccept={handleCookieAccept}
          colors={colors}
        />
      )}
    </div>
  );
};
