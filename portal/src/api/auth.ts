import apiClient from './client';

interface LoginResponse {
  access_token?: string;
  refresh_token?: string;
  expires_in?: number;
  token_type?: string;
  mfa_required?: boolean;
}

interface Claims {
  sub: string;
  email: string;
  role: string;
  tenant: string;
  iat: number;
  exp: number;
}

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

    if (response.data.access_token && response.data.refresh_token) {
      sessionStorage.setItem('access_token', response.data.access_token);
      sessionStorage.setItem('refresh_token', response.data.refresh_token);

      const claims = parseJwt(response.data.access_token);
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
  const refreshToken = sessionStorage.getItem('refresh_token');

  try {
    if (refreshToken) {
      await apiClient.post('/auth/logout', { refresh_token: refreshToken });
    }
  } catch (error) {
    console.log('[auth] Logout API call failed, clearing tokens locally');
  } finally {
    sessionStorage.removeItem('access_token');
    sessionStorage.removeItem('refresh_token');
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
    Array.isArray(roles) && roles.length > 0
      ? String(roles[0])
      : String(payload.role ?? 'viewer');
  const email = typeof payload.email === 'string' ? payload.email : String(payload.sub ?? '');
  return { ...payload, email, role } as unknown as Claims;
}

export function getStoredToken(): string | null {
  return sessionStorage.getItem('access_token');
}

export function getStoredClaims(): Claims | null {
  const token = getStoredToken();
  return token ? parseJwt(token) : null;
}
