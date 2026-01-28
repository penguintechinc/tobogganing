import type { ReactNode } from 'react';

/**
 * API configuration for login endpoint
 */
export interface LoginApiConfig {
  /** URL for the login endpoint */
  loginUrl: string;
  /** HTTP method (default: POST) */
  method?: 'POST' | 'PUT';
  /** Additional headers to include */
  headers?: Record<string, string>;
}

/**
 * Login request payload
 */
export interface LoginPayload {
  email: string;
  password: string;
  rememberMe?: boolean;
  captchaToken?: string;
  mfaCode?: string;
}

/**
 * Login response from API
 */
export interface LoginResponse {
  success: boolean;
  /** User data on successful login */
  user?: {
    id: string;
    email: string;
    name?: string;
    roles?: string[];
  };
  /** Authentication token */
  token?: string;
  /** Refresh token */
  refreshToken?: string;
  /** Set to true if MFA is required */
  mfaRequired?: boolean;
  /** Error message if login failed */
  error?: string;
  /** Error code for programmatic handling */
  errorCode?: string;
}

/**
 * Branding configuration
 */
export interface BrandingConfig {
  /** Application name displayed on login page */
  appName: string;
  /** Logo - can be URL string or React component */
  logo?: ReactNode | string;
  /** Logo width in pixels (default: 300) */
  logoWidth?: number;
  /** Tagline displayed below app name */
  tagline?: string;
  /** GitHub repository for footer link (e.g., "penguintechinc/project-name") */
  githubRepo?: string;
}

/**
 * CAPTCHA configuration (ALTCHA provider)
 */
export interface CaptchaConfig {
  /** Enable CAPTCHA */
  enabled: boolean;
  /** CAPTCHA provider (only altcha supported) */
  provider: 'altcha';
  /** Number of failed attempts before showing CAPTCHA (default: 3) */
  failedAttemptsThreshold?: number;
  /** URL to fetch CAPTCHA challenge */
  challengeUrl: string;
  /** Timeout window in milliseconds for resetting failed attempts (default: 900000 - 15 min) */
  resetTimeoutMs?: number;
}

/**
 * MFA/2FA configuration
 */
export interface MFAConfig {
  /** Enable MFA support */
  enabled: boolean;
  /** Number of digits in MFA code (default: 6) */
  codeLength?: number;
  /** Allow "Remember this device" option */
  allowRememberDevice?: boolean;
}

/**
 * GDPR Cookie Consent configuration
 */
export interface GDPRConfig {
  /** Enable GDPR consent banner (default: true) */
  enabled?: boolean;
  /** URL to privacy policy page */
  privacyPolicyUrl: string;
  /** URL to cookie policy page (optional) */
  cookiePolicyUrl?: string;
  /** Custom consent message */
  consentText?: string;
  /** Show "Manage Preferences" option (default: true) */
  showPreferences?: boolean;
}

/**
 * OAuth2 provider configuration
 */
interface OAuth2ProviderBase {
  clientId: string;
  redirectUri?: string;
  scopes?: string[];
}

/**
 * Built-in OAuth2 providers with pre-configured URLs and branding
 */
export interface BuiltInOAuth2Provider extends OAuth2ProviderBase {
  provider: 'google' | 'github' | 'microsoft' | 'apple' | 'twitch' | 'discord';
}

/**
 * Custom OAuth2 provider configuration
 */
export interface CustomOAuth2Provider extends OAuth2ProviderBase {
  provider: 'oauth2';
  authUrl: string;
  label: string;
  icon?: ReactNode;
  buttonColor?: string;
  textColor?: string;
}

/**
 * OpenID Connect (OIDC) provider configuration
 */
export interface OIDCProvider {
  provider: 'oidc';
  /** OIDC issuer URL for auto-discovery */
  issuerUrl: string;
  clientId: string;
  redirectUri?: string;
  scopes?: string[];
  label?: string;
  icon?: ReactNode;
}

/**
 * SAML provider configuration
 */
export interface SAMLProvider {
  provider: 'saml';
  /** Identity Provider SSO URL */
  idpSsoUrl: string;
  /** Service Provider Entity ID */
  entityId: string;
  /** Assertion Consumer Service URL */
  acsUrl: string;
  /** IdP certificate for signature validation */
  certificate?: string;
  label?: string;
  icon?: ReactNode;
}

/**
 * Union type for all social login configurations
 */
export type SocialLoginConfig =
  | BuiltInOAuth2Provider
  | CustomOAuth2Provider
  | OIDCProvider
  | SAMLProvider;

/**
 * Color configuration for theming
 */
export interface LoginColorConfig {
  // Page colors
  pageBackground: string;
  cardBackground: string;
  cardBorder: string;

  // Text colors
  titleText: string;
  subtitleText: string;
  labelText: string;
  inputText: string;
  placeholderText: string;
  errorText: string;
  linkText: string;
  linkHoverText: string;

  // Input colors
  inputBackground: string;
  inputBorder: string;
  inputFocusBorder: string;
  inputFocusRing: string;

  // Button colors
  primaryButton: string;
  primaryButtonHover: string;
  primaryButtonText: string;
  secondaryButton: string;
  secondaryButtonHover: string;
  secondaryButtonText: string;
  secondaryButtonBorder: string;

  // Social button colors (default styling)
  socialButtonBackground: string;
  socialButtonBorder: string;
  socialButtonText: string;
  socialButtonHover: string;

  // Divider
  dividerColor: string;
  dividerText: string;

  // Footer
  footerText: string;
  footerLinkText: string;

  // GDPR banner
  bannerBackground: string;
  bannerText: string;
  bannerBorder: string;
}

/**
 * Main props for LoginPageBuilder component
 */
export interface LoginPageBuilderProps {
  // Required props
  /** API endpoint configuration */
  api: LoginApiConfig;
  /** Branding configuration (logo, app name, etc.) */
  branding: BrandingConfig;
  /** Callback when login succeeds */
  onSuccess: (response: LoginResponse) => void;

  // GDPR Cookie Consent
  /** GDPR consent configuration */
  gdpr?: GDPRConfig;

  // CAPTCHA configuration
  /** CAPTCHA configuration (ALTCHA) */
  captcha?: CaptchaConfig;

  // MFA configuration
  /** MFA/2FA configuration */
  mfa?: MFAConfig;

  // UI options
  /** Custom color theme */
  colors?: Partial<LoginColorConfig>;
  /** Show "Forgot Password" link (default: true) */
  showForgotPassword?: boolean;
  /** URL for forgot password page */
  forgotPasswordUrl?: string;
  /** Callback for forgot password click */
  onForgotPassword?: () => void;
  /** Show "Sign Up" link (default: true) */
  showSignUp?: boolean;
  /** URL for sign up page */
  signUpUrl?: string;
  /** Callback for sign up click */
  onSignUp?: () => void;
  /** Show "Remember Me" checkbox (default: true) */
  showRememberMe?: boolean;
  /** Additional CSS class for the page container */
  className?: string;

  // Social/SSO logins
  /** Social login provider configurations */
  socialLogins?: SocialLoginConfig[];

  // Error handling
  /** Callback when login fails */
  onError?: (error: Error, errorCode?: string) => void;
  /** Custom error message transformer */
  transformErrorMessage?: (error: string, code?: string) => string;
}

/**
 * Cookie consent state
 */
export interface CookieConsentState {
  accepted: boolean;
  essential: boolean;
  functional: boolean;
  analytics: boolean;
  marketing: boolean;
  timestamp?: number;
}

/**
 * CAPTCHA hook return type
 */
export interface UseCaptchaReturn {
  /** Whether CAPTCHA should be shown */
  showCaptcha: boolean;
  /** Current failed attempt count */
  failedAttempts: number;
  /** Increment failed attempt counter */
  incrementFailedAttempts: () => void;
  /** Reset failed attempt counter */
  resetFailedAttempts: () => void;
  /** CAPTCHA verification token */
  captchaToken: string | null;
  /** Set CAPTCHA token after verification */
  setCaptchaToken: (token: string | null) => void;
  /** Whether CAPTCHA is verified */
  isVerified: boolean;
}

/**
 * MFA modal props
 */
export interface MFAModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit: (code: string, rememberDevice?: boolean) => void;
  codeLength?: number;
  allowRememberDevice?: boolean;
  colors?: Partial<LoginColorConfig>;
  isSubmitting?: boolean;
  error?: string;
}

/**
 * MFA input props
 */
export interface MFAInputProps {
  length: number;
  value: string;
  onChange: (value: string) => void;
  onComplete?: (code: string) => void;
  disabled?: boolean;
  error?: boolean;
  colors?: Partial<LoginColorConfig>;
}

/**
 * CAPTCHA widget props
 */
export interface CaptchaWidgetProps {
  challengeUrl: string;
  onVerified: (token: string) => void;
  onError?: (error: Error) => void;
  colors?: Partial<LoginColorConfig>;
}

/**
 * Social login button props
 */
export interface SocialLoginButtonsProps {
  providers: SocialLoginConfig[];
  onProviderClick: (provider: SocialLoginConfig) => void;
  colors?: Partial<LoginColorConfig>;
  disabled?: boolean;
}

/**
 * Cookie consent props
 */
export interface CookieConsentProps {
  gdpr: GDPRConfig;
  onAccept: (consent: CookieConsentState) => void;
  colors?: Partial<LoginColorConfig>;
}

/**
 * Footer props
 */
export interface FooterProps {
  githubRepo?: string;
  colors?: Partial<LoginColorConfig>;
}
