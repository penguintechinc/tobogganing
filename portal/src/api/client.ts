import axios, { AxiosInstance } from 'axios';
import { CSRF_COOKIE_NAME, clearCachedClaims, getCookie } from './authStorage';

const STATE_CHANGING_METHODS = new Set(['post', 'put', 'patch', 'delete']);
const CSRF_HEADER_NAME = 'X-CSRF-Token';

let refreshPromise: Promise<void> | null = null;

const apiClient: AxiosInstance = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
  // The server authenticates browser requests via HttpOnly access_token/
  // refresh_token cookies - never a stored token - so every request must
  // carry credentials for the cookie to be sent/accepted cross-origin.
  withCredentials: true,
});

// Request interceptor: double-submit CSRF. On state-changing requests
// (POST/PUT/PATCH/DELETE) that authenticate via cookie, echo the readable
// csrf_token cookie back as a header; the server rejects a mismatch. GET/HEAD
// never carry it - they don't need it and it would be a no-op if they did.
apiClient.interceptors.request.use((config) => {
  const method = (config.method ?? 'get').toLowerCase();
  if (STATE_CHANGING_METHODS.has(method)) {
    const csrfToken = getCookie(CSRF_COOKIE_NAME);
    if (csrfToken) {
      config.headers[CSRF_HEADER_NAME] = csrfToken;
    }
  }
  return config;
});

// Response interceptor: handle 401 with single-flight cookie refresh
apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Auth endpoints own their 401 semantics (bad credentials, dead refresh
    // token) - never treat them as an expired session, or the login page's
    // own error state would be wiped by a redirect/reload.
    const requestUrl: string = originalRequest?.url ?? '';
    if (requestUrl.includes('/auth/')) {
      return Promise.reject(error);
    }

    if (error.response?.status === 401 && !originalRequest._retry) {
      originalRequest._retry = true;

      try {
        // Single-flight: queue behind one refresh promise. No body needed -
        // the server reads the refresh_token cookie itself; the CSRF header
        // for this POST is attached by the request interceptor above.
        if (!refreshPromise) {
          refreshPromise = apiClient.post('/auth/refresh-token').then(() => undefined);
        }

        await refreshPromise;

        // Retry original request - the rotated cookies ride along automatically.
        return apiClient(originalRequest);
      } catch (refreshError) {
        console.log('[apiClient] Refresh failed, redirecting to login');
        clearCachedClaims();
        window.location.href = '/login';
        return Promise.reject(refreshError);
      } finally {
        refreshPromise = null;
      }
    }

    return Promise.reject(error);
  }
);

export default apiClient;
