export { FormModalBuilder } from './FormModalBuilder';
export type { FormField, FormTab, FormModalBuilderProps, ColorConfig } from './FormModalBuilder';

export { SidebarMenu } from './SidebarMenu';
export type { MenuItem, MenuCategory, SidebarColorConfig, SidebarMenuProps } from './SidebarMenu';

export {
  ConsoleVersion,
  AppConsoleVersion,
  parseVersion,
  logVersionToConsole,
  useVersionInfo,
  useApiVersionInfo,
} from './ConsoleVersion';
export type {
  VersionInfo,
  ConsoleStyleConfig,
  ConsoleVersionProps,
  AppConsoleVersionProps,
  ApiStatusResponse,
} from './ConsoleVersion';

// LoginPageBuilder exports
export {
  LoginPageBuilder,
  ELDER_LOGIN_THEME,
  mergeWithElderTheme,
  useCaptcha,
  useCookieConsent,
  MFAModal,
  MFAInput,
  CaptchaWidget,
  SocialLoginButtons,
  LoginDivider,
  CookieConsent,
  Footer,
  GoogleIcon,
  GitHubIcon,
  MicrosoftIcon,
  AppleIcon,
  TwitchIcon,
  DiscordIcon,
  SSOIcon,
  EnterpriseIcon,
  buildOAuth2Url,
  buildCustomOAuth2Url,
  buildOIDCUrl,
  generateState,
  validateState,
  getProviderLabel,
  getProviderColors,
  buildSAMLRequest,
  buildSAMLRedirectUrl,
  initiateSAMLLogin,
  validateRelayState,
} from './LoginPageBuilder';
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
} from './LoginPageBuilder';
