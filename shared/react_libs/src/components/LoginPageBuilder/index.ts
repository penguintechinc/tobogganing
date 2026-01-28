// Main component export
export { LoginPageBuilder } from './LoginPageBuilder';

// Type exports
export type {
  LoginPageBuilderProps,
  LoginApiConfig,
  LoginPayload,
  LoginResponse,
  BrandingConfig,
  CaptchaConfig,
  MFAConfig,
  GDPRConfig,
  SocialLoginConfig,
  BuiltInOAuth2Provider,
  CustomOAuth2Provider,
  OIDCProvider,
  SAMLProvider,
  LoginColorConfig,
  CookieConsentState,
  UseCaptchaReturn,
  MFAModalProps,
  MFAInputProps,
  CaptchaWidgetProps,
  SocialLoginButtonsProps,
  CookieConsentProps,
  FooterProps,
} from './types';

// Theme exports
export { ELDER_LOGIN_THEME, mergeWithElderTheme } from './themes/elderTheme';

// Hook exports (for advanced usage)
export { useCaptcha } from './hooks/useCaptcha';
export { useCookieConsent } from './hooks/useCookieConsent';

// Utility exports (for custom implementations)
export {
  buildOAuth2Url,
  buildCustomOAuth2Url,
  buildOIDCUrl,
  generateState,
  validateState,
  getProviderLabel,
  getProviderColors,
} from './utils/oauth';

export {
  buildSAMLRequest,
  buildSAMLRedirectUrl,
  buildSAMLPostForm,
  initiateSAMLLogin,
  initiateSAMLPostLogin,
  validateRelayState,
  getStoredRequestId,
  clearSAMLSession,
} from './utils/saml';

// Sub-component exports (for custom layouts)
export { MFAModal } from './components/MFAModal';
export { MFAInput } from './components/MFAInput';
export { CaptchaWidget } from './components/CaptchaWidget';
export { SocialLoginButtons, LoginDivider } from './components/SocialLoginButtons';
export { CookieConsent } from './components/CookieConsent';
export { Footer } from './components/Footer';

// Icon exports (for custom buttons)
export {
  GoogleIcon,
  GitHubIcon,
  MicrosoftIcon,
  AppleIcon,
  TwitchIcon,
  DiscordIcon,
  SSOIcon,
  EnterpriseIcon,
} from './components/icons';
