import apiClient from './client';
import { cacheClaims, clearCachedClaims, readCachedClaims, type Claims } from './authStorage';

interface LoginResponse {
  access_token?: string;
  refresh_token?: string;
  expires_in?: number;
  token_type?: string;
  mfa_required?: boolean;
}

export type { Claims };

export async function login(
  email: string,
  password: string,
  mfaToken?: string
): Promise<{ mfaRequired: boolean; claims?: Claims }> {
  console.log(`[auth] Login { email: "${email.split('@')[0]}@..." }`);

  try {
    const response = await apiClient.post<LoginResponse>('/auth/login', {
      email,
      password,
      mfa_token: mfaToken,
    });

    if (response.data.mfa_required) {
      return { mfaRequired: true };
    }

    // The server sets the access_token/refresh_token/csrf_token cookies
    // itself (this call carries credentials via apiClient) - the JSON body
    // still echoes access_token only so we can decode display claims once,
    // immediately, without ever persisting the token itself.
    if (response.data.access_token) {
      const claims = parseJwt(response.data.access_token);
      cacheClaims(claims);
      console.log(`[auth] Login success { tenant: "${claims.tenant}" }`);
      return { mfaRequired: false, claims };
    }

    return { mfaRequired: false };
  } catch (error) {
    console.log('[auth] Login failed');
    throw error;
  }
}

export async function logout(): Promise<void> {
  console.log('[auth] Logout');

  try {
    // No body needed - the server reads the refresh_token cookie and clears
    // all three auth cookies regardless of outcome.
    await apiClient.post('/auth/logout');
  } catch (error) {
    console.log('[auth] Logout API call failed, clearing local state anyway');
  } finally {
    clearCachedClaims();
  }
}

export function parseJwt(token: string): Claims {
  const parts = token.split('.');
  if (parts.length !== 3) {
    throw new Error('Invalid token');
  }
  const base64Url = parts[1] as string;
  const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
  const jsonPayload = decodeURIComponent(
    atob(base64)
      .split('')
      .map((c) => {
        const hex = c.charCodeAt(0).toString(16);
        return `%${`00${hex}`.slice(-2)}`;
      })
      .join('')
  );
  const payload = JSON.parse(jsonPayload) as Record<string, unknown>;
  // Normalize: real backend tokens carry roles: [..] and no email claim —
  // derive a singular role and a display identity that never crash the UI.
  const roles = payload.roles;
  const role =
    Array.isArray(roles) && roles.length > 0 ? String(roles[0]) : String(payload.role ?? 'viewer');
  const email = typeof payload.email === 'string' ? payload.email : String(payload.sub ?? '');
  return { ...payload, email, role } as unknown as Claims;
}

/**
 * Synchronous auth-state hydration for app start / page reload. There is no
 * client-readable access token anymore (HttpOnly), so this reads the cached
 * claims from the last login/refresh - self-invalidating against the
 * readable csrf_token cookie so a stale per-tab cache never survives a
 * server-side logout. This is a UI hint only; every API call is still
 * authorized server-side from the cookie on each request.
 */
export function getStoredClaims(): Claims | null {
  return readCachedClaims();
}
