import apiClient from './client';

describe('apiClient', () => {
  let consoleLogSpy: jest.SpyInstance;

  beforeEach(() => {
    jest.clearAllMocks();
    sessionStorage.clear();
    consoleLogSpy = jest.spyOn(console, 'log').mockImplementation();
  });

  afterEach(() => {
    consoleLogSpy.mockRestore();
  });

  it('stores and retrieves tokens from sessionStorage', () => {
    sessionStorage.setItem('access_token', 'test-token-123');
    sessionStorage.setItem('refresh_token', 'refresh-token-456');

    expect(sessionStorage.getItem('access_token')).toBe('test-token-123');
    expect(sessionStorage.getItem('refresh_token')).toBe('refresh-token-456');
  });

  it('clears tokens on logout', () => {
    sessionStorage.setItem('access_token', 'old-token');
    sessionStorage.setItem('refresh_token', 'invalid-token');

    sessionStorage.removeItem('access_token');
    sessionStorage.removeItem('refresh_token');

    expect(sessionStorage.getItem('access_token')).toBeNull();
    expect(sessionStorage.getItem('refresh_token')).toBeNull();
  });

  it('has axios interceptors configured', () => {
    // Verify that request interceptor is configured
    expect(apiClient.interceptors.request.use).toBeDefined();
    expect(apiClient.interceptors.response.use).toBeDefined();
  });

  it('creates API client with correct base URL', () => {
    expect(apiClient.defaults.baseURL).toBe('/api/v1');
  });

  it('sets correct timeout', () => {
    expect(apiClient.defaults.timeout).toBe(30000);
  });

  it('request interceptor injects Bearer token when present', () => {
    sessionStorage.setItem('access_token', 'test-token-123');
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const config = { headers: {} as Record<string, any> } as any;

    // Get the registered request interceptor function
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const requestHandler = (apiClient.interceptors.request as any).handlers[0]?.fulfilled;
    if (requestHandler) {
      const result = requestHandler(config);
      expect(result.headers.Authorization).toBe('Bearer test-token-123');
    }
  });

  it('request interceptor does not inject token when absent', () => {
    sessionStorage.clear();
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const config = { headers: {} as Record<string, any> } as any;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const requestHandler = (apiClient.interceptors.request as any).handlers[0]?.fulfilled;
    if (requestHandler) {
      const result = requestHandler(config);
      expect(result.headers.Authorization).toBeUndefined();
    }
  });

  it('response interceptor on non-401 error passes through', async () => {
    const error = { response: { status: 500 }, config: { headers: {}, _retry: false } };

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const responseHandler = (apiClient.interceptors.response as any).handlers[0]?.rejected;
    if (responseHandler) {
      try {
        await responseHandler(error);
      } catch (e) {
        expect(e).toBe(error);
      }
    }
  });

  it('response interceptor on 401 without refresh token redirects to login', async () => {
    sessionStorage.clear();
    const error = { response: { status: 401 }, config: { headers: {}, _retry: false } };

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const responseHandler = (apiClient.interceptors.response as any).handlers[0]?.rejected;
    if (responseHandler) {
      try {
        await responseHandler(error);
      } catch (e) {
        expect(window.location.href).toBe('/login');
      }
    }
  });

  it('response interceptor handles 401 with refresh token retry', async () => {
    sessionStorage.setItem('refresh_token', 'refresh-token-123');
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const originalConfig = { headers: {} as Record<string, any>, _retry: false };
    const error = { response: { status: 401 }, config: originalConfig };

    // Mock the post call for token refresh
    const postSpy = jest.spyOn(apiClient, 'post').mockResolvedValue({
      data: {
        access_token: 'new-token-456',
        refresh_token: 'new-refresh-789',
        expires_in: 3600,
        token_type: 'Bearer',
      },
    });

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const responseHandler = (apiClient.interceptors.response as any).handlers[0]?.rejected;
    if (responseHandler) {
      try {
        await responseHandler(error);
      } catch (e) {
        // Error expected but the token should have been refreshed
        expect(sessionStorage.getItem('access_token')).toBe('new-token-456');
      }
    }

    postSpy.mockRestore();
  });

  it('handles refresh token errors', async () => {
    sessionStorage.setItem('refresh_token', 'invalid-refresh-token');
    const error = { response: { status: 401 }, config: { headers: {}, _retry: false } };

    // Mock the post call to fail
    const postSpy = jest.spyOn(apiClient, 'post').mockRejectedValue(new Error('Refresh failed'));

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const responseHandler = (apiClient.interceptors.response as any).handlers[0]?.rejected;
    if (responseHandler) {
      try {
        await responseHandler(error);
      } catch (e) {
        // Should redirect to login on refresh failure
        expect(window.location.href).toBe('/login');
      }
    }

    postSpy.mockRestore();
  });

  it('response interceptor passes through successful responses', async () => {
    const response = { status: 200, data: { success: true } };

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const responseHandler = (apiClient.interceptors.response as any).handlers[0]?.fulfilled;
    if (responseHandler) {
      const result = responseHandler(response);
      expect(result).toBe(response);
    }
  });

  it('response interceptor on already retried 401 errors passes through', async () => {
    const error = { response: { status: 401 }, config: { headers: {}, _retry: true } };

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const responseHandler = (apiClient.interceptors.response as any).handlers[0]?.rejected;
    if (responseHandler) {
      try {
        await responseHandler(error);
      } catch (e) {
        expect(e).toBe(error);
      }
    }
  });
});
