import React, { useCallback } from 'react';
import type { SocialLoginButtonsProps, SocialLoginConfig, LoginColorConfig } from '../types';
import { ELDER_LOGIN_THEME } from '../themes/elderTheme';
import { getProviderLabel, getProviderColors } from '../utils/oauth';
import {
  GoogleIcon,
  GitHubIcon,
  MicrosoftIcon,
  AppleIcon,
  TwitchIcon,
  DiscordIcon,
  SSOIcon,
  EnterpriseIcon,
} from './icons';

/**
 * Logger utility for social login buttons
 */
const log = {
  debug: (message: string, data?: Record<string, unknown>) => {
    if (process.env.NODE_ENV === 'development') {
      console.debug(`[LoginPage:Social] ${message}`, data ?? '');
    }
  },
  info: (message: string, data?: Record<string, unknown>) => {
    console.info(`[LoginPage:Social] ${message}`, data ?? '');
  },
};

/**
 * Get icon component for a provider
 */
function getProviderIcon(config: SocialLoginConfig): React.ReactNode {
  // Check for custom icon first
  if ('icon' in config && config.icon) {
    return config.icon;
  }

  switch (config.provider) {
    case 'google':
      return <GoogleIcon className="w-5 h-5" />;
    case 'github':
      return <GitHubIcon className="w-5 h-5" />;
    case 'microsoft':
      return <MicrosoftIcon className="w-5 h-5" />;
    case 'apple':
      return <AppleIcon className="w-5 h-5" />;
    case 'twitch':
      return <TwitchIcon className="w-5 h-5" />;
    case 'discord':
      return <DiscordIcon className="w-5 h-5" />;
    case 'oidc':
      return <SSOIcon className="w-5 h-5" />;
    case 'saml':
      return <EnterpriseIcon className="w-5 h-5" />;
    case 'oauth2':
      return <SSOIcon className="w-5 h-5" />;
    default:
      return <SSOIcon className="w-5 h-5" />;
  }
}

/**
 * Get button styling for a provider
 */
function getButtonStyles(
  config: SocialLoginConfig,
  theme: LoginColorConfig
): { className: string; style?: React.CSSProperties } {
  // Check for custom styling
  if (config.provider === 'oauth2' && config.buttonColor) {
    return {
      className: `w-full flex items-center justify-center gap-3 py-2.5 px-4 rounded-lg font-medium border transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed`,
      style: {
        backgroundColor: config.buttonColor,
        color: config.textColor || '#ffffff',
        borderColor: config.buttonColor,
      },
    };
  }

  // Built-in provider colors
  const brandColors = getProviderColors(config.provider);
  if (brandColors) {
    return {
      className: `w-full flex items-center justify-center gap-3 py-2.5 px-4 rounded-lg font-medium border transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed ${brandColors.background} ${brandColors.text} ${brandColors.hover}`,
    };
  }

  // Default to theme-based styling
  return {
    className: `w-full flex items-center justify-center gap-3 py-2.5 px-4 rounded-lg font-medium border transition-colors duration-200 disabled:opacity-50 disabled:cursor-not-allowed ${theme.socialButtonBackground} ${theme.socialButtonText} ${theme.socialButtonBorder} ${theme.socialButtonHover}`,
  };
}

/**
 * Social login buttons component.
 *
 * Features:
 * - Built-in icons and branding for major providers
 * - Support for custom OAuth2, OIDC, and SAML providers
 * - Brand-consistent button styling
 * - Disabled state during login
 */
export const SocialLoginButtons: React.FC<SocialLoginButtonsProps> = ({
  providers,
  onProviderClick,
  colors,
  disabled = false,
}) => {
  const theme: LoginColorConfig = { ...ELDER_LOGIN_THEME, ...colors };

  const handleClick = useCallback(
    (config: SocialLoginConfig) => {
      log.info('Social login button clicked', { provider: config.provider });
      onProviderClick(config);
    },
    [onProviderClick]
  );

  if (!providers || providers.length === 0) {
    return null;
  }

  return (
    <div className="space-y-3">
      {providers.map((config, index) => {
        const label = getProviderLabel(config);
        const icon = getProviderIcon(config);
        const buttonStyles = getButtonStyles(config, theme);

        return (
          <button
            key={`${config.provider}-${index}`}
            type="button"
            onClick={() => handleClick(config)}
            disabled={disabled}
            className={buttonStyles.className}
            style={buttonStyles.style}
          >
            {icon}
            <span>{label}</span>
          </button>
        );
      })}
    </div>
  );
};

/**
 * Divider component for "or" separator between login methods
 */
export const LoginDivider: React.FC<{ colors?: Partial<LoginColorConfig> }> = ({ colors }) => {
  const theme: LoginColorConfig = { ...ELDER_LOGIN_THEME, ...colors };

  return (
    <div className="relative my-6">
      <div className="absolute inset-0 flex items-center">
        <div className={`w-full border-t ${theme.dividerColor}`} />
      </div>
      <div className="relative flex justify-center text-sm">
        <span className={`px-4 ${theme.cardBackground} ${theme.dividerText}`}>
          or continue with
        </span>
      </div>
    </div>
  );
};
