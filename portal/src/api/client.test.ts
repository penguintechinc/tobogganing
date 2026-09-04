import apiClient from './client';

function setCookie(name: string, value: string): void {
  document.cookie = `${name}=${value}; path=/`;
}

function clearCookie(name: string): void {
  document.cookie = `${name}=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT`;
}

describe('apiClient', () => {
  let consoleLogSpy: jest.SpyInstance;

  beforeEach(() => {
    jest.clearAllMocks();
    clearCookie('csrf_token');
    sessionStorage.clear();
    consoleLogSpy = jest.spyOn(console, 'log').mockImplementation();
  });

  afterEach(() => {
    consoleLogSpy.mockRestore();
    clearCookie('csrf_token');
  });

  it('sends credentials (cookies) on every request', () => {
    expect(apiClient.defaults.withCredentials).toBe(true);
  });

  it('has axios interceptors configured', () => {
    expect(apiClient.interceptors.request.use).toBeDefined();
    expect(apiClient.interceptors.response.use).toBeDefined();
  });

  it('creates API client with correct base URL', () => {
    expect(apiClient.defaults.baseURL).toBe('/api/v1');
  });

  it('sets correct timeout', () => {
    expect(apiClient.defaults.timeout).toBe(30000);
  });

  it('request interceptor attaches X-CSRF-Token on POST when csrf_token cookie is present', () => {
    setCookie('csrf_token', 'csrf-abc-123');
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const config = { method: 'post', headers: {} as Record<string, any> } as any;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const requestHandler = (apiClient.interceptors.request as any).handlers[0]?.fulfilled;
    const result = requestHandler(config);
    expect(result.headers['X-CSRF-Token']).toBe('csrf-abc-123');
  });

  it('request interceptor does not attach X-CSRF-Token on GET', () => {
    setCookie('csrf_token', 'csrf-abc-123');
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const config = { method: 'get', headers: {} as Record<string, any> } as any;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const requestHandler = (apiClient.interceptors.request as any).handlers[0]?.fulfilled;
    const result = requestHandler(config);
    expect(result.headers['X-CSRF-Token']).toBeUndefined();
  });

  it('request interceptor omits X-CSRF-Token when no csrf_token cookie is present', () => {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const config = { method: 'put', headers: {} as Record<string, any> } as any;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const requestHandler = (apiClient.interceptors.request as any).handlers[0]?.fulfilled;
    const result = requestHandler(config);
    expect(result.headers['X-CSRF-Token']).toBeUndefined();
  });

  it('request interceptor treats DELETE as state-changing', () => {
    setCookie('csrf_token', 'csrf-delete-1');
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const config = { method: 'delete', headers: {} as Record<string, any> } as any;

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const requestHandler = (apiClient.interceptors.request as any).handlers[0]?.fulfilled;
    const result = requestHandler(config);
    expect(result.headers['X-CSRF-Token']).toBe('csrf-delete-1');
  });

  it('response interceptor on non-401 error passes through', async () => {
    const error = { response: { status: 500 }, config: { headers: {}, _retry: false } };

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const responseHandler = (apiClient.interceptors.response as any).handlers[0]?.rejected;
    await expect(responseHandler(error)).rejects.toBe(error);
  });

  it('response interceptor on 401 refreshes via cookie and retries', async () => {
    // `apiClient(originalRequest)` calls the axios instance directly (not via
    // `.post`/`.get`), so stub the transport at the adapter level (scoped to
    // this one request's config, not the global default) to avoid a real
    // network call while still exercising the real retry code path.
    const adapterMock = jest.fn().mockResolvedValue({
      data: { ok: true },
      status: 200,
      statusText: 'OK',
      headers: {},
      config: {},
    });
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const originalConfig: any = { headers: {}, _retry: false, adapter: adapterMock };
    const error = { response: { status: 401 }, config: originalConfig };

    const postSpy = jest.spyOn(apiClient, 'post').mockResolvedValue({ data: {} });

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const responseHandler = (apiClient.interceptors.response as any).handlers[0]?.rejected;
    const result = await responseHandler(error);

    expect(postSpy).toHaveBeenCalledWith('/auth/refresh-token');
    expect(originalConfig._retry).toBe(true);
    expect(adapterMock).toHaveBeenCalled();
    expect((result as { data: { ok: boolean } }).data.ok).toBe(true);

    postSpy.mockRestore();
  });

  it('response interceptor redirects to /login when refresh fails, clearing cached claims', async () => {
    sessionStorage.setItem('auth_claims', JSON.stringify({ sub: 'u1' }));
    const error = { response: { status: 401 }, config: { headers: {}, _retry: false } };

    const postSpy = jest.spyOn(apiClient, 'post').mockRejectedValue(new Error('refresh failed'));

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const responseHandler = (apiClient.interceptors.response as any).handlers[0]?.rejected;
    await expect(responseHandler(error)).rejects.toThrow('refresh failed');

    expect(window.location.href).toBe('/login');
    expect(sessionStorage.getItem('auth_claims')).toBeNull();

    postSpy.mockRestore();
  });

  it('response interceptor passes through successful responses', () => {
    const response = { status: 200, data: { success: true } };

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const responseHandler = (apiClient.interceptors.response as any).handlers[0]?.fulfilled;
    const result = responseHandler(response);
    expect(result).toBe(response);
  });

  it('response interceptor on already-retried 401 passes through', async () => {
    const error = { response: { status: 401 }, config: { headers: {}, _retry: true } };

    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    const responseHandler = (apiClient.interceptors.response as any).handlers[0]?.rejected;
    await expect(responseHandler(error)).rejects.toBe(error);
  });
});

describe('auth endpoint 401 passthrough', () => {
  it('rejects auth-endpoint 401s without refresh or redirect', async () => {
    const interceptors = apiClient.interceptors.response as unknown as {
      handlers: { rejected: (e: unknown) => Promise<unknown> }[];
    };
    const handler = interceptors.handlers[0]!.rejected;
    const error = {
      config: { url: '/auth/login' },
      response: { status: 401 },
    };
    const postSpy = jest.spyOn(apiClient, 'post');
    await expect(handler(error)).rejects.toBe(error);
    // No refresh attempted, no redirect (location mock untouched by this path)
    expect(postSpy).not.toHaveBeenCalled();
    postSpy.mockRestore();
  });
});
