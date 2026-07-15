import axios, { AxiosInstance } from 'axios';

interface TokenPair {
  access_token: string;
  refresh_token: string;
  expires_in: number;
  token_type: string;
}

let refreshPromise: Promise<TokenPair> | null = null;

const apiClient: AxiosInstance = axios.create({
  baseURL: '/api/v1',
  timeout: 30000,
});

// Request interceptor: inject Bearer token
apiClient.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Response interceptor: handle 401 with single-flight refresh
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
      const refreshToken = sessionStorage.getItem('refresh_token');

      if (!refreshToken) {
        window.location.href = '/login';
        return Promise.reject(error);
      }

      try {
        // Single-flight: queue behind one refresh promise
        if (!refreshPromise) {
          refreshPromise = (async () => {
            const res = await apiClient.post<TokenPair>('/auth/refresh', {
              refresh_token: refreshToken,
            });
            return res.data;
          })();
        }

        const tokens = await refreshPromise;
        const { access_token, refresh_token: newRefreshToken } = tokens;

        sessionStorage.setItem('access_token', access_token);
        sessionStorage.setItem('refresh_token', newRefreshToken);

        // Retry original request with new token
        originalRequest.headers.Authorization = `Bearer ${access_token}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        console.log('[apiClient] Refresh failed, redirecting to login');
        sessionStorage.removeItem('access_token');
        sessionStorage.removeItem('refresh_token');
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
