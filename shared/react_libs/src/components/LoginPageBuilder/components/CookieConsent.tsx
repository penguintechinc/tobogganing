import React, { useState, useCallback } from 'react';
import type { CookieConsentProps, CookieConsentState, LoginColorConfig } from '../types';
import { ELDER_LOGIN_THEME } from '../themes/elderTheme';

/**
 * Logger utility for cookie consent
 */
const log = {
  debug: (message: string, data?: Record<string, unknown>) => {
    if (process.env.NODE_ENV === 'development') {
      console.debug(`[LoginPage:GDPR] ${message}`, data ?? '');
    }
  },
};

/**
 * Cookie preferences modal for granular consent control
 */
const PreferencesModal: React.FC<{
  isOpen: boolean;
  onClose: () => void;
  onSave: (preferences: Partial<CookieConsentState>) => void;
  theme: LoginColorConfig;
  privacyPolicyUrl: string;
  cookiePolicyUrl?: string;
}> = ({ isOpen, onClose, onSave, theme, privacyPolicyUrl, cookiePolicyUrl }) => {
  const [functional, setFunctional] = useState(false);
  const [analytics, setAnalytics] = useState(false);
  const [marketing, setMarketing] = useState(false);

  const handleSave = useCallback(() => {
    log.debug('Saving cookie preferences', { functional, analytics, marketing });
    onSave({ functional, analytics, marketing });
  }, [functional, analytics, marketing, onSave]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 z-[60] overflow-y-auto"
      aria-labelledby="cookie-preferences-title"
      role="dialog"
      aria-modal="true"
    >
      <div className="flex min-h-screen items-center justify-center p-4">
        <div
          className="fixed inset-0 bg-black/60 transition-opacity"
          aria-hidden="true"
          onClick={onClose}
        />

        <div
          className={`relative w-full max-w-lg transform rounded-xl ${theme.cardBackground} border ${theme.cardBorder} p-6 shadow-2xl`}
        >
          <h2 id="cookie-preferences-title" className={`text-lg font-semibold ${theme.titleText} mb-4`}>
            Cookie Preferences
          </h2>

          <div className="space-y-4 mb-6">
            {/* Essential cookies - always on */}
            <div className={`p-4 rounded-lg border ${theme.cardBorder}`}>
              <div className="flex items-center justify-between">
                <div>
                  <h3 className={`font-medium ${theme.labelText}`}>Essential Cookies</h3>
                  <p className={`text-sm ${theme.subtitleText}`}>
                    Required for the website to function. Cannot be disabled.
                  </p>
                </div>
                <div className={`px-3 py-1 rounded text-sm ${theme.primaryButton} ${theme.primaryButtonText}`}>
                  Always On
                </div>
              </div>
            </div>

            {/* Functional cookies */}
            <div className={`p-4 rounded-lg border ${theme.cardBorder}`}>
              <div className="flex items-center justify-between">
                <div className="flex-1 mr-4">
                  <h3 className={`font-medium ${theme.labelText}`}>Functional Cookies</h3>
                  <p className={`text-sm ${theme.subtitleText}`}>
                    Enable personalized features and remember your preferences.
                  </p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={functional}
                    onChange={(e) => setFunctional(e.target.checked)}
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-amber-500 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-amber-500"></div>
                </label>
              </div>
            </div>

            {/* Analytics cookies */}
            <div className={`p-4 rounded-lg border ${theme.cardBorder}`}>
              <div className="flex items-center justify-between">
                <div className="flex-1 mr-4">
                  <h3 className={`font-medium ${theme.labelText}`}>Analytics Cookies</h3>
                  <p className={`text-sm ${theme.subtitleText}`}>
                    Help us understand how visitors interact with our website.
                  </p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={analytics}
                    onChange={(e) => setAnalytics(e.target.checked)}
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-amber-500 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-amber-500"></div>
                </label>
              </div>
            </div>

            {/* Marketing cookies */}
            <div className={`p-4 rounded-lg border ${theme.cardBorder}`}>
              <div className="flex items-center justify-between">
                <div className="flex-1 mr-4">
                  <h3 className={`font-medium ${theme.labelText}`}>Marketing Cookies</h3>
                  <p className={`text-sm ${theme.subtitleText}`}>
                    Used to deliver personalized advertisements.
                  </p>
                </div>
                <label className="relative inline-flex items-center cursor-pointer">
                  <input
                    type="checkbox"
                    checked={marketing}
                    onChange={(e) => setMarketing(e.target.checked)}
                    className="sr-only peer"
                  />
                  <div className="w-11 h-6 bg-slate-700 peer-focus:outline-none peer-focus:ring-2 peer-focus:ring-amber-500 rounded-full peer peer-checked:after:translate-x-full after:content-[''] after:absolute after:top-[2px] after:left-[2px] after:bg-white after:rounded-full after:h-5 after:w-5 after:transition-all peer-checked:bg-amber-500"></div>
                </label>
              </div>
            </div>
          </div>

          <div className="flex flex-col sm:flex-row gap-3">
            <button
              onClick={handleSave}
              className={`flex-1 py-2.5 px-4 rounded-lg font-medium ${theme.primaryButton} ${theme.primaryButtonText} ${theme.primaryButtonHover} transition-colors`}
            >
              Save Preferences
            </button>
            <button
              onClick={onClose}
              className={`flex-1 py-2.5 px-4 rounded-lg font-medium border ${theme.secondaryButton} ${theme.secondaryButtonText} ${theme.secondaryButtonBorder} ${theme.secondaryButtonHover} transition-colors`}
            >
              Cancel
            </button>
          </div>

          <p className={`mt-4 text-xs text-center ${theme.subtitleText}`}>
            Learn more in our{' '}
            <a href={privacyPolicyUrl} className={`${theme.linkText} ${theme.linkHoverText} underline`} target="_blank" rel="noopener noreferrer">
              Privacy Policy
            </a>
            {cookiePolicyUrl && (
              <>
                {' '}and{' '}
                <a href={cookiePolicyUrl} className={`${theme.linkText} ${theme.linkHoverText} underline`} target="_blank" rel="noopener noreferrer">
                  Cookie Policy
                </a>
              </>
            )}
          </p>
        </div>
      </div>
    </div>
  );
};

/**
 * GDPR cookie consent banner.
 *
 * Features:
 * - Appears on first visit before login form is interactive
 * - Options: Accept All, Essential Only, Manage Preferences
 * - Preferences modal for granular control
 * - Consent stored in localStorage with timestamp
 */
export const CookieConsent: React.FC<CookieConsentProps> = ({
  gdpr,
  onAccept,
  colors,
}) => {
  const theme: LoginColorConfig = { ...ELDER_LOGIN_THEME, ...colors };
  const [showPreferences, setShowPreferences] = useState(false);

  const handleAcceptAll = useCallback(() => {
    log.debug('User accepted all cookies');
    onAccept({
      accepted: true,
      essential: true,
      functional: true,
      analytics: true,
      marketing: true,
      timestamp: Date.now(),
    });
  }, [onAccept]);

  const handleAcceptEssential = useCallback(() => {
    log.debug('User accepted essential cookies only');
    onAccept({
      accepted: true,
      essential: true,
      functional: false,
      analytics: false,
      marketing: false,
      timestamp: Date.now(),
    });
  }, [onAccept]);

  const handleSavePreferences = useCallback(
    (preferences: Partial<CookieConsentState>) => {
      setShowPreferences(false);
      onAccept({
        accepted: true,
        essential: true,
        functional: preferences.functional ?? false,
        analytics: preferences.analytics ?? false,
        marketing: preferences.marketing ?? false,
        timestamp: Date.now(),
      });
    },
    [onAccept]
  );

  const consentText = gdpr.consentText ||
    'We use cookies to enhance your experience. By continuing to visit this site you agree to our use of cookies.';

  return (
    <>
      {/* Cookie consent banner */}
      <div
        className={`fixed bottom-0 left-0 right-0 z-50 ${theme.bannerBackground} border-t ${theme.bannerBorder} shadow-lg`}
      >
        <div className="max-w-4xl mx-auto px-4 py-4 sm:px-6">
          <div className="flex flex-col sm:flex-row items-start sm:items-center gap-4">
            {/* Cookie icon */}
            <div className="hidden sm:flex shrink-0 w-10 h-10 rounded-full bg-amber-500/10 items-center justify-center">
              <svg
                className="w-5 h-5 text-amber-400"
                fill="none"
                viewBox="0 0 24 24"
                stroke="currentColor"
                strokeWidth={2}
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M12 8v4m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z"
                />
              </svg>
            </div>

            {/* Text content */}
            <div className="flex-1">
              <p className={`text-sm ${theme.bannerText}`}>
                {consentText}{' '}
                <a
                  href={gdpr.privacyPolicyUrl}
                  className={`${theme.linkText} ${theme.linkHoverText} underline`}
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  Privacy Policy
                </a>
                {gdpr.cookiePolicyUrl && (
                  <>
                    {' | '}
                    <a
                      href={gdpr.cookiePolicyUrl}
                      className={`${theme.linkText} ${theme.linkHoverText} underline`}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      Cookie Policy
                    </a>
                  </>
                )}
              </p>
            </div>

            {/* Action buttons */}
            <div className="flex flex-wrap gap-2 shrink-0">
              <button
                onClick={handleAcceptAll}
                className={`px-4 py-2 text-sm font-medium rounded-lg ${theme.primaryButton} ${theme.primaryButtonText} ${theme.primaryButtonHover} transition-colors`}
              >
                Accept All
              </button>
              <button
                onClick={handleAcceptEssential}
                className={`px-4 py-2 text-sm font-medium rounded-lg border ${theme.secondaryButton} ${theme.secondaryButtonText} ${theme.secondaryButtonBorder} ${theme.secondaryButtonHover} transition-colors`}
              >
                Essential Only
              </button>
              {gdpr.showPreferences !== false && (
                <button
                  onClick={() => setShowPreferences(true)}
                  className={`px-4 py-2 text-sm font-medium ${theme.linkText} ${theme.linkHoverText} transition-colors`}
                >
                  Manage Preferences
                </button>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Preferences modal */}
      <PreferencesModal
        isOpen={showPreferences}
        onClose={() => setShowPreferences(false)}
        onSave={handleSavePreferences}
        theme={theme}
        privacyPolicyUrl={gdpr.privacyPolicyUrl}
        cookiePolicyUrl={gdpr.cookiePolicyUrl}
      />
    </>
  );
};
