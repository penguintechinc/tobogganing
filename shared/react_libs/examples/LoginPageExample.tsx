/**
 * LoginPageBuilder Examples
 *
 * This file demonstrates various configurations for the LoginPageBuilder component.
 * Copy and adapt these examples for your application.
 */

import React from 'react';
import { LoginPageBuilder, LoginResponse } from '@penguin/react_libs';

/**
 * Example 1: Basic Login Page
 *
 * Minimal configuration with just email/password authentication.
 */
export function BasicLoginExample() {
  const handleSuccess = (response: LoginResponse) => {
    console.log('Login successful!', response.user?.email);
    // Store token and redirect
    if (response.token) {
      localStorage.setItem('authToken', response.token);
    }
    window.location.href = '/dashboard';
  };

  return (
    <LoginPageBuilder
      api={{
        loginUrl: '/api/v1/auth/login',
      }}
      branding={{
        appName: 'My Application',
        tagline: 'Welcome back! Please sign in to continue.',
        githubRepo: 'penguintechinc/my-app',
      }}
      onSuccess={handleSuccess}
      gdpr={{
        enabled: true,
        privacyPolicyUrl: '/privacy',
      }}
    />
  );
}

/**
 * Example 2: Login with Logo and Full Branding
 *
 * Includes logo, custom tagline, and sign up/forgot password links.
 */
export function BrandedLoginExample() {
  const handleSuccess = (response: LoginResponse) => {
    console.log('Login successful!', response.user?.email);
    window.location.href = '/dashboard';
  };

  return (
    <LoginPageBuilder
      api={{
        loginUrl: '/api/v1/auth/login',
      }}
      branding={{
        appName: 'WaddleBot',
        logo: '/images/waddlebot-logo.png',
        logoWidth: 250,
        tagline: 'Your AI-powered assistant for everything',
        githubRepo: 'penguintechinc/waddlebot',
      }}
      onSuccess={handleSuccess}
      gdpr={{
        enabled: true,
        privacyPolicyUrl: '/privacy',
        cookiePolicyUrl: '/cookies',
        showPreferences: true,
      }}
      showForgotPassword={true}
      forgotPasswordUrl="/auth/forgot-password"
      showSignUp={true}
      signUpUrl="/auth/register"
      showRememberMe={true}
    />
  );
}

/**
 * Example 3: Login with CAPTCHA
 *
 * Shows CAPTCHA after 3 failed login attempts.
 * Requires backend endpoint for ALTCHA challenges.
 */
export function CaptchaLoginExample() {
  const handleSuccess = (response: LoginResponse) => {
    console.log('Login successful!');
    window.location.href = '/dashboard';
  };

  const handleError = (error: Error, errorCode?: string) => {
    console.error('Login error:', errorCode, error.message);
    // Custom error tracking
  };

  return (
    <LoginPageBuilder
      api={{
        loginUrl: '/api/v1/auth/login',
      }}
      branding={{
        appName: 'Secure Portal',
        tagline: 'Enterprise-grade security',
        githubRepo: 'penguintechinc/secure-portal',
      }}
      onSuccess={handleSuccess}
      onError={handleError}
      gdpr={{
        enabled: true,
        privacyPolicyUrl: '/privacy',
      }}
      captcha={{
        enabled: true,
        provider: 'altcha',
        challengeUrl: '/api/v1/captcha/challenge',
        failedAttemptsThreshold: 3,
        resetTimeoutMs: 900000, // 15 minutes
      }}
    />
  );
}

/**
 * Example 4: Login with MFA/2FA Support
 *
 * Shows MFA modal when API returns mfaRequired: true.
 */
export function MFALoginExample() {
  const handleSuccess = (response: LoginResponse) => {
    console.log('Login successful with MFA!');
    window.location.href = '/dashboard';
  };

  return (
    <LoginPageBuilder
      api={{
        loginUrl: '/api/v1/auth/login',
      }}
      branding={{
        appName: 'Secure Banking',
        tagline: 'Two-factor authentication enabled',
        githubRepo: 'penguintechinc/banking-app',
      }}
      onSuccess={handleSuccess}
      gdpr={{
        enabled: true,
        privacyPolicyUrl: '/privacy',
      }}
      mfa={{
        enabled: true,
        codeLength: 6,
        allowRememberDevice: true,
      }}
    />
  );
}

/**
 * Example 5: Login with Social Providers
 *
 * Includes OAuth2 social login buttons for Google, GitHub, and Microsoft.
 */
export function SocialLoginExample() {
  const handleSuccess = (response: LoginResponse) => {
    console.log('Login successful!');
    window.location.href = '/dashboard';
  };

  return (
    <LoginPageBuilder
      api={{
        loginUrl: '/api/v1/auth/login',
      }}
      branding={{
        appName: 'Community Platform',
        tagline: 'Join millions of users',
        githubRepo: 'penguintechinc/community',
      }}
      onSuccess={handleSuccess}
      gdpr={{
        enabled: true,
        privacyPolicyUrl: '/privacy',
      }}
      socialLogins={[
        {
          provider: 'google',
          clientId: process.env.REACT_APP_GOOGLE_CLIENT_ID || 'your-google-client-id',
          redirectUri: `${window.location.origin}/auth/callback/google`,
        },
        {
          provider: 'github',
          clientId: process.env.REACT_APP_GITHUB_CLIENT_ID || 'your-github-client-id',
          redirectUri: `${window.location.origin}/auth/callback/github`,
          scopes: ['user:email', 'read:user'],
        },
        {
          provider: 'microsoft',
          clientId: process.env.REACT_APP_MICROSOFT_CLIENT_ID || 'your-microsoft-client-id',
          redirectUri: `${window.location.origin}/auth/callback/microsoft`,
        },
      ]}
    />
  );
}

/**
 * Example 6: Enterprise Login with OIDC and SAML
 *
 * Includes enterprise SSO options alongside regular login.
 */
export function EnterpriseLoginExample() {
  const handleSuccess = (response: LoginResponse) => {
    console.log('Login successful!');
    window.location.href = '/dashboard';
  };

  return (
    <LoginPageBuilder
      api={{
        loginUrl: '/api/v1/auth/login',
      }}
      branding={{
        appName: 'Enterprise Suite',
        tagline: 'Sign in with your corporate credentials',
        githubRepo: 'penguintechinc/enterprise-suite',
      }}
      onSuccess={handleSuccess}
      gdpr={{
        enabled: true,
        privacyPolicyUrl: '/privacy',
      }}
      socialLogins={[
        // OIDC provider (e.g., Okta, Auth0, Keycloak)
        {
          provider: 'oidc',
          issuerUrl: 'https://your-company.okta.com',
          clientId: 'your-oidc-client-id',
          redirectUri: `${window.location.origin}/auth/callback/oidc`,
          scopes: ['openid', 'email', 'profile'],
          label: 'Sign in with Okta',
        },
        // SAML provider for enterprise SSO
        {
          provider: 'saml',
          idpSsoUrl: 'https://idp.enterprise.com/saml/sso',
          entityId: 'https://your-app.com/saml/metadata',
          acsUrl: `${window.location.origin}/auth/saml/acs`,
          label: 'Enterprise SSO',
        },
      ]}
    />
  );
}

/**
 * Example 7: Full-Featured Login Page
 *
 * Combines all features: CAPTCHA, MFA, social login, and enterprise SSO.
 */
export function FullFeaturedLoginExample() {
  const handleSuccess = (response: LoginResponse) => {
    console.log('Login successful!', {
      userId: response.user?.id,
      hasToken: !!response.token,
    });

    if (response.token) {
      localStorage.setItem('authToken', response.token);
    }
    if (response.refreshToken) {
      localStorage.setItem('refreshToken', response.refreshToken);
    }

    window.location.href = '/dashboard';
  };

  const handleError = (error: Error, errorCode?: string) => {
    // Send to error tracking service
    console.error('Login failed:', { errorCode, message: error.message });
  };

  const transformError = (error: string, code?: string) => {
    // Map error codes to user-friendly messages
    const errorMessages: Record<string, string> = {
      INVALID_CREDENTIALS: 'Invalid email or password. Please try again.',
      ACCOUNT_LOCKED: 'Your account has been locked. Please contact support.',
      MFA_REQUIRED: 'Please enter your verification code.',
      NETWORK_ERROR: 'Unable to connect. Please check your internet connection.',
    };
    return errorMessages[code || ''] || error;
  };

  return (
    <LoginPageBuilder
      api={{
        loginUrl: '/api/v1/auth/login',
        method: 'POST',
        headers: {
          'X-App-Version': '1.0.0',
        },
      }}
      branding={{
        appName: 'MarchProxy',
        logo: '/images/marchproxy-logo.png',
        logoWidth: 280,
        tagline: 'Enterprise API Gateway & Load Balancer',
        githubRepo: 'penguintechinc/marchproxy',
      }}
      onSuccess={handleSuccess}
      onError={handleError}
      transformErrorMessage={transformError}
      gdpr={{
        enabled: true,
        privacyPolicyUrl: '/legal/privacy',
        cookiePolicyUrl: '/legal/cookies',
        consentText: 'We use cookies to ensure you get the best experience. By continuing, you agree to our cookie policy.',
        showPreferences: true,
      }}
      captcha={{
        enabled: true,
        provider: 'altcha',
        challengeUrl: '/api/v1/captcha/challenge',
        failedAttemptsThreshold: 3,
      }}
      mfa={{
        enabled: true,
        codeLength: 6,
        allowRememberDevice: true,
      }}
      socialLogins={[
        {
          provider: 'github',
          clientId: process.env.REACT_APP_GITHUB_CLIENT_ID || '',
          scopes: ['user:email'],
        },
        {
          provider: 'google',
          clientId: process.env.REACT_APP_GOOGLE_CLIENT_ID || '',
        },
        {
          provider: 'oidc',
          issuerUrl: 'https://auth.penguintech.io',
          clientId: 'marchproxy',
          label: 'Penguin Tech SSO',
        },
      ]}
      showForgotPassword={true}
      forgotPasswordUrl="/auth/forgot-password"
      showSignUp={true}
      signUpUrl="/auth/register"
      showRememberMe={true}
    />
  );
}

/**
 * Example 8: Custom Themed Login
 *
 * Demonstrates custom color theming.
 */
export function CustomThemedLoginExample() {
  const handleSuccess = (response: LoginResponse) => {
    window.location.href = '/dashboard';
  };

  return (
    <LoginPageBuilder
      api={{
        loginUrl: '/api/v1/auth/login',
      }}
      branding={{
        appName: 'Custom Theme App',
        tagline: 'With custom purple theme',
      }}
      onSuccess={handleSuccess}
      gdpr={{
        enabled: true,
        privacyPolicyUrl: '/privacy',
      }}
      colors={{
        // Purple theme instead of gold
        pageBackground: 'bg-gray-900',
        cardBackground: 'bg-gray-800',
        cardBorder: 'border-gray-700',
        titleText: 'text-purple-400',
        subtitleText: 'text-gray-400',
        labelText: 'text-purple-300',
        linkText: 'text-purple-400',
        linkHoverText: 'hover:text-purple-300',
        primaryButton: 'bg-purple-500',
        primaryButtonHover: 'hover:bg-purple-600',
        primaryButtonText: 'text-white',
        inputFocusBorder: 'focus:border-purple-500',
        inputFocusRing: 'focus:ring-purple-500',
        footerLinkText: 'text-purple-400',
      }}
    />
  );
}

export default FullFeaturedLoginExample;
