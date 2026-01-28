import type { SocialLoginConfig, BuiltInOAuth2Provider, CustomOAuth2Provider, OIDCProvider } from '../types';

/**
 * Logger utility for OAuth - never logs secrets or tokens
 */
const log = {
  debug: (message: string, data?: Record<string, unknown>) => {
    if (process.env.NODE_ENV === 'development') {
      console.debug(`[LoginPage:OAuth] ${message}`, data ? sanitizeOAuthLog(data) : '');
    }
  },
  info: (message: string, data?: Record<string, unknown>) => {
    console.info(`[LoginPage:OAuth] ${message}`, data ? sanitizeOAuthLog(data) : '');
  },
  error: (message: string, error?: unknown) => {
    console.error(`[LoginPage:OAuth] ${message}`, error instanceof Error ? error.message : error);
  },
};

function sanitizeOAuthLog(data: Record<string, unknown>): Record<string, unknown> {
  const sanitized = { ...data };
  // Never log client secrets, tokens, or codes
  if ('clientSecret' in sanitized) sanitized.clientSecret = '[REDACTED]';
  if ('client_secret' in sanitized) sanitized.client_secret = '[REDACTED]';
  if ('code' in sanitized) sanitized.code = '[REDACTED]';
  if ('access_token' in sanitized) sanitized.access_token = '[REDACTED]';
  if ('refresh_token' in sanitized) sanitized.refresh_token = '[REDACTED]';
  if ('id_token' in sanitized) sanitized.id_token = '[REDACTED]';
  // Truncate URLs for readability
  if (typeof sanitized.redirectUri === 'string' && sanitized.redirectUri.length > 50) {
    sanitized.redirectUri = sanitized.redirectUri.substring(0, 50) + '...';
  }
  return sanitized;
}

/**
 * Built-in OAuth2 provider configurations
 */
const OAUTH2_PROVIDERS: Record<
  BuiltInOAuth2Provider['provider'],
  { authUrl: string; defaultScopes: string[]; label: string }
> = {
  google: {
    authUrl: 'https://accounts.google.com/o/oauth2/v2/auth',
    defaultScopes: ['openid', 'email', 'profile'],
    label: 'Continue with Google',
  },
  github: {
    authUrl: 'https://github.com/login/oauth/authorize',
    defaultScopes: ['user:email'],
    label: 'Continue with GitHub',
  },
  microsoft: {
    authUrl: 'https://login.microsoftonline.com/common/oauth2/v2.0/authorize',
    defaultScopes: ['openid', 'email', 'profile'],
    label: 'Continue with Microsoft',
  },
  apple: {
    authUrl: 'https://appleid.apple.com/auth/authorize',
    defaultScopes: ['name', 'email'],
    label: 'Continue with Apple',
  },
  twitch: {
    authUrl: 'https://id.twitch.tv/oauth2/authorize',
    defaultScopes: ['user:read:email'],
    label: 'Continue with Twitch',
  },
  discord: {
    authUrl: 'https://discord.com/api/oauth2/authorize',
    defaultScopes: ['identify', 'email'],
    label: 'Continue with Discord',
  },
};

/**
 * Generate a cryptographically random state parameter for CSRF protection
 */
export function generateState(): string {
  const array = new Uint8Array(32);
  crypto.getRandomValues(array);
  return Array.from(array, (byte) => byte.toString(16).padStart(2, '0')).join('');
}

/**
 * Generate PKCE code verifier (43-128 characters)
 */
export function generateCodeVerifier(): string {
  const array = new Uint8Array(32);
  crypto.getRandomValues(array);
  return base64UrlEncode(array);
}

/**
 * Generate PKCE code challenge from verifier
 */
export async function generateCodeChallenge(verifier: string): Promise<string> {
  const encoder = new TextEncoder();
  const data = encoder.encode(verifier);
  const digest = await crypto.subtle.digest('SHA-256', data);
  return base64UrlEncode(new Uint8Array(digest));
}

/**
 * Base64 URL encode (no padding, URL-safe characters)
 */
function base64UrlEncode(buffer: Uint8Array): string {
  const base64 = btoa(String.fromCharCode(...buffer));
  return base64.replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

/**
 * Build OAuth2 authorization URL for built-in providers
 */
export function buildOAuth2Url(config: BuiltInOAuth2Provider): string {
  const providerConfig = OAUTH2_PROVIDERS[config.provider];
  if (!providerConfig) {
    log.error('Unknown OAuth2 provider', { provider: config.provider });
    throw new Error(`Unknown OAuth2 provider: ${config.provider}`);
  }

  const state = generateState();
  // Store state in sessionStorage for validation on callback
  sessionStorage.setItem('oauth_state', state);

  const params = new URLSearchParams({
    client_id: config.clientId,
    redirect_uri: config.redirectUri || `${window.location.origin}/auth/callback`,
    response_type: 'code',
    scope: (config.scopes || providerConfig.defaultScopes).join(' '),
    state,
  });

  // Provider-specific parameters
  if (config.provider === 'google') {
    params.set('access_type', 'offline');
    params.set('prompt', 'consent');
  } else if (config.provider === 'apple') {
    params.set('response_mode', 'form_post');
  }

  const url = `${providerConfig.authUrl}?${params.toString()}`;

  log.info('Built OAuth2 URL', {
    provider: config.provider,
    redirectUri: config.redirectUri,
    scopes: config.scopes || providerConfig.defaultScopes,
  });

  return url;
}

/**
 * Build OAuth2 authorization URL for custom providers
 */
export function buildCustomOAuth2Url(config: CustomOAuth2Provider): string {
  const state = generateState();
  sessionStorage.setItem('oauth_state', state);

  const params = new URLSearchParams({
    client_id: config.clientId,
    redirect_uri: config.redirectUri || `${window.location.origin}/auth/callback`,
    response_type: 'code',
    state,
  });

  if (config.scopes && config.scopes.length > 0) {
    params.set('scope', config.scopes.join(' '));
  }

  const url = `${config.authUrl}?${params.toString()}`;

  log.info('Built custom OAuth2 URL', {
    label: config.label,
    authUrl: config.authUrl,
  });

  return url;
}

/**
 * Build OIDC authorization URL with auto-discovery support
 */
export async function buildOIDCUrl(config: OIDCProvider): Promise<string> {
  const discoveryUrl = `${config.issuerUrl.replace(/\/$/, '')}/.well-known/openid-configuration`;

  log.debug('Fetching OIDC discovery document', { discoveryUrl });

  try {
    const response = await fetch(discoveryUrl);
    if (!response.ok) {
      throw new Error(`OIDC discovery failed: ${response.status}`);
    }

    const discovery = await response.json();
    const authEndpoint = discovery.authorization_endpoint;

    if (!authEndpoint) {
      throw new Error('No authorization_endpoint in OIDC discovery');
    }

    const state = generateState();
    const nonce = generateState(); // Nonce for ID token validation
    sessionStorage.setItem('oauth_state', state);
    sessionStorage.setItem('oidc_nonce', nonce);

    const params = new URLSearchParams({
      client_id: config.clientId,
      redirect_uri: config.redirectUri || `${window.location.origin}/auth/callback`,
      response_type: 'code',
      scope: (config.scopes || ['openid', 'email', 'profile']).join(' '),
      state,
      nonce,
    });

    const url = `${authEndpoint}?${params.toString()}`;

    log.info('Built OIDC URL', {
      issuer: config.issuerUrl,
      authEndpoint,
    });

    return url;
  } catch (error) {
    log.error('OIDC discovery failed', error);
    throw error;
  }
}

/**
 * Validate OAuth state parameter to prevent CSRF attacks
 */
export function validateState(receivedState: string): boolean {
  const storedState = sessionStorage.getItem('oauth_state');
  const isValid = storedState === receivedState;

  if (!isValid) {
    log.error('OAuth state validation failed - possible CSRF attack');
  } else {
    log.debug('OAuth state validated successfully');
    sessionStorage.removeItem('oauth_state');
  }

  return isValid;
}

/**
 * Get display label for a social login provider
 */
export function getProviderLabel(config: SocialLoginConfig): string {
  if ('label' in config && config.label) {
    return config.label;
  }

  if (config.provider in OAUTH2_PROVIDERS) {
    return OAUTH2_PROVIDERS[config.provider as BuiltInOAuth2Provider['provider']].label;
  }

  if (config.provider === 'oidc') {
    return 'Continue with SSO';
  }

  if (config.provider === 'saml') {
    return 'Continue with Enterprise SSO';
  }

  return 'Continue with SSO';
}

/**
 * Get brand colors for built-in providers
 */
export function getProviderColors(
  provider: string
): { background: string; text: string; hover: string } | null {
  const colors: Record<string, { background: string; text: string; hover: string }> = {
    google: {
      background: 'bg-white',
      text: 'text-gray-700',
      hover: 'hover:bg-gray-50',
    },
    github: {
      background: 'bg-gray-900',
      text: 'text-white',
      hover: 'hover:bg-gray-800',
    },
    microsoft: {
      background: 'bg-white',
      text: 'text-gray-700',
      hover: 'hover:bg-gray-50',
    },
    apple: {
      background: 'bg-black',
      text: 'text-white',
      hover: 'hover:bg-gray-900',
    },
    twitch: {
      background: 'bg-[#9146FF]',
      text: 'text-white',
      hover: 'hover:bg-[#7B2EE8]',
    },
    discord: {
      background: 'bg-[#5865F2]',
      text: 'text-white',
      hover: 'hover:bg-[#4752C4]',
    },
  };

  return colors[provider] || null;
}
