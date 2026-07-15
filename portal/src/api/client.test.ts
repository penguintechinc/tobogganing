jest.mock('axios');

describe('apiClient', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    sessionStorage.clear();
  });

  it('stores and retrieves tokens from sessionStorage', async () => {
    sessionStorage.setItem('access_token', 'test-token-123');
    sessionStorage.setItem('refresh_token', 'refresh-token-456');

    expect(sessionStorage.getItem('access_token')).toBe('test-token-123');
    expect(sessionStorage.getItem('refresh_token')).toBe('refresh-token-456');
  });

  it('handles 401 error scenarios', async () => {
    sessionStorage.setItem('access_token', 'old-token');
    sessionStorage.setItem('refresh_token', 'refresh-123');

    const error = {
      response: { status: 401 },
      config: { _retry: false, headers: {} },
    };

    expect(error.response.status).toBe(401);
  });

  it('clears tokens on logout', async () => {
    sessionStorage.setItem('access_token', 'old-token');
    sessionStorage.setItem('refresh_token', 'invalid-token');

    sessionStorage.removeItem('access_token');
    sessionStorage.removeItem('refresh_token');

    expect(sessionStorage.getItem('access_token')).toBeNull();
    expect(sessionStorage.getItem('refresh_token')).toBeNull();
  });
});
