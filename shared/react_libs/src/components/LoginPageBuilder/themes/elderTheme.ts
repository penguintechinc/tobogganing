import type { LoginColorConfig } from '../types';

/**
 * Elder-style dark theme with gold/amber accents.
 * Matches the project template's default dark mode styling.
 */
export const ELDER_LOGIN_THEME: LoginColorConfig = {
  // Page colors - dark-950 background
  pageBackground: 'bg-slate-950',
  cardBackground: 'bg-slate-800',
  cardBorder: 'border-slate-700',

  // Text colors - gold/amber for primary, slate for secondary
  titleText: 'text-amber-400',
  subtitleText: 'text-slate-400',
  labelText: 'text-amber-300',
  inputText: 'text-slate-100',
  placeholderText: 'placeholder-slate-500',
  errorText: 'text-red-400',
  linkText: 'text-amber-400',
  linkHoverText: 'hover:text-amber-300',

  // Input colors - dark inputs with gold focus
  inputBackground: 'bg-slate-900',
  inputBorder: 'border-slate-600',
  inputFocusBorder: 'focus:border-amber-500',
  inputFocusRing: 'focus:ring-amber-500',

  // Button colors - gold primary, slate secondary
  primaryButton: 'bg-amber-500',
  primaryButtonHover: 'hover:bg-amber-600',
  primaryButtonText: 'text-slate-900',
  secondaryButton: 'bg-slate-700',
  secondaryButtonHover: 'hover:bg-slate-600',
  secondaryButtonText: 'text-slate-100',
  secondaryButtonBorder: 'border-slate-600',

  // Social button colors
  socialButtonBackground: 'bg-slate-700',
  socialButtonBorder: 'border-slate-600',
  socialButtonText: 'text-slate-100',
  socialButtonHover: 'hover:bg-slate-600',

  // Divider
  dividerColor: 'border-slate-600',
  dividerText: 'text-slate-500',

  // Footer
  footerText: 'text-slate-500',
  footerLinkText: 'text-amber-400',

  // GDPR banner
  bannerBackground: 'bg-slate-800',
  bannerText: 'text-slate-300',
  bannerBorder: 'border-slate-700',
};

/**
 * Merge partial color config with Elder theme defaults
 */
export function mergeWithElderTheme(
  partial?: Partial<LoginColorConfig>
): LoginColorConfig {
  if (!partial) return ELDER_LOGIN_THEME;
  return { ...ELDER_LOGIN_THEME, ...partial };
}
