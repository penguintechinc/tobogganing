/**
 * Client-side helpers for the cookie-based auth flow. The server owns the
 * access_token/refresh_token cookies exclusively (HttpOnly - this module
 * never reads or writes either); it only reads the readable csrf_token
 * cookie (for the double-submit CSRF header) and caches the last-decoded
 * JWT claims in sessionStorage purely for synchronous UI hydration across
 * page reloads. Nothing here is a credential - losing it never grants API
 * access, it only affects what the UI shows before the first request lands.
 */

export const CSRF_COOKIE_NAME = 'csrf_token';

const CLAIMS_CACHE_KEY = 'auth_claims';

export interface Claims {
  sub: string;
  email: string;
  role: string;
  tenant: string;
  iat: number;
  exp: number;
}

/** Reads a cookie value by name from document.cookie; null if absent (or HttpOnly). */
export function getCookie(name: string): string | null {
  const match = document.cookie.match(new RegExp(`(?:^|;\\s*)${name}=([^;]*)`));
  const value = match?.[1];
  return value ? decodeURIComponent(value) : null;
}

/**
 * True when the server has an active cookie session for this browser. The
 * csrf_token cookie is set/rotated/cleared in lockstep with the HttpOnly
 * access_token/refresh_token cookies, so its presence is a reliable, JS-
 * readable proxy for "the server thinks this browser is logged in" without
 * ever exposing the tokens themselves.
 */
export function hasSessionCookie(): boolean {
  return getCookie(CSRF_COOKIE_NAME) !== null;
}

/** Caches decoded JWT claims (never the token) for synchronous UI hydration on reload. */
export function cacheClaims(claims: Claims): void {
  sessionStorage.setItem(CLAIMS_CACHE_KEY, JSON.stringify(claims));
}

/**
 * Reads cached claims for initial UI hydration. Invalidates (and drops) the
 * cache whenever the session cookie is gone, so a stale per-tab cache never
 * outlives the server-side session it describes (e.g. logout in another tab).
 */
export function readCachedClaims(): Claims | null {
  if (!hasSessionCookie()) {
    sessionStorage.removeItem(CLAIMS_CACHE_KEY);
    return null;
  }

  const raw = sessionStorage.getItem(CLAIMS_CACHE_KEY);
  if (!raw) {
    return null;
  }

  try {
    return JSON.parse(raw) as Claims;
  } catch {
    return null;
  }
}

/** Clears the cached claims. Call on logout or any hard auth failure. */
export function clearCachedClaims(): void {
  sessionStorage.removeItem(CLAIMS_CACHE_KEY);
}
