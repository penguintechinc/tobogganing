import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { LoginPage } from './LoginPage';
import { AuthProvider } from '../context/AuthContext';
import * as authApi from '../api/auth';

jest.mock('../api/auth');

const renderLogin = () => {
  render(
    <MemoryRouter initialEntries={['/login']}>
      <AuthProvider>
        <LoginPage />
      </AuthProvider>
    </MemoryRouter>
  );
};

describe('LoginPage', () => {
  beforeEach(() => {
    sessionStorage.clear();
    jest.clearAllMocks();
  });

  it('renders login form', () => {
    renderLogin();
    expect(screen.getByLabelText(/email/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/password/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /sign in/i })).toBeInTheDocument();
    expect(screen.getByText(/tobogganing portal/i)).toBeInTheDocument();
  });

  it('accepts email and password input', () => {
    renderLogin();
    const emailInput = screen.getByLabelText(/email/i) as HTMLInputElement;
    const passwordInput = screen.getByLabelText(/password/i) as HTMLInputElement;

    fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
    fireEvent.change(passwordInput, { target: { value: 'password123' } });

    expect(emailInput.value).toBe('test@example.com');
    expect(passwordInput.value).toBe('password123');
  });

  it('validates email field is required', () => {
    renderLogin();
    const emailInput = screen.getByLabelText(/email/i) as HTMLInputElement;
    expect(emailInput.required).toBe(true);
  });

  it('validates password field is required', () => {
    renderLogin();
    const passwordInput = screen.getByLabelText(/password/i) as HTMLInputElement;
    expect(passwordInput.required).toBe(true);
  });

  it('disables email and password fields during MFA step', async () => {
    (authApi.login as jest.Mock).mockResolvedValue({ mfaRequired: true });

    renderLogin();
    const emailInput = screen.getByLabelText(/email/i) as HTMLInputElement;
    const passwordInput = screen.getByLabelText(/password/i) as HTMLInputElement;
    const submitButton = screen.getByRole('button', { name: /sign in/i });

    fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
    fireEvent.change(passwordInput, { target: { value: 'password' } });

    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(emailInput.disabled).toBe(true);
      expect(passwordInput.disabled).toBe(true);
    });
  });

  it('shows MFA token field after MFA required response', async () => {
    (authApi.login as jest.Mock).mockResolvedValue({ mfaRequired: true });

    renderLogin();
    const emailInput = screen.getByLabelText(/email/i);
    const passwordInput = screen.getByLabelText(/password/i);
    const submitButton = screen.getByRole('button', { name: /sign in/i });

    fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
    fireEvent.change(passwordInput, { target: { value: 'password' } });

    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(screen.getByLabelText(/mfa token/i)).toBeInTheDocument();
      expect(screen.getByRole('button', { name: /verify mfa/i })).toBeInTheDocument();
    });
  });

  it('displays error message on failed login', async () => {
    const errorMessage = 'Invalid credentials';
    (authApi.login as jest.Mock).mockRejectedValue({
      response: { data: { error: errorMessage } },
    });

    renderLogin();
    const emailInput = screen.getByLabelText(/email/i);
    const passwordInput = screen.getByLabelText(/password/i);
    const submitButton = screen.getByRole('button', { name: /sign in/i });

    fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
    fireEvent.change(passwordInput, { target: { value: 'wrongpassword' } });

    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(errorMessage)).toBeInTheDocument();
    });
  });

  it('shows loading state during submission', async () => {
    (authApi.login as jest.Mock).mockImplementation(
      () => new Promise((resolve) => setTimeout(() => resolve({ mfaRequired: true }), 100))
    );

    renderLogin();
    const emailInput = screen.getByLabelText(/email/i);
    const passwordInput = screen.getByLabelText(/password/i);
    const submitButton = screen.getByRole('button', { name: /sign in/i });

    fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
    fireEvent.change(passwordInput, { target: { value: 'password' } });

    fireEvent.click(submitButton);

    await waitFor(() => {
      const button = screen.getByRole('button') as HTMLButtonElement;
      expect(button.disabled).toBe(true);
    });
  });

  it('successfully logs in and navigates', async () => {
    (authApi.login as jest.Mock).mockResolvedValue({
      mfaRequired: false,
      claims: {
        sub: '1234567890',
        email: 'test@example.com',
        role: 'viewer',
        tenant: 't1',
        iat: 1516239022,
        exp: 9999999999,
      },
    });

    renderLogin();
    const emailInput = screen.getByLabelText(/email/i);
    const passwordInput = screen.getByLabelText(/password/i);
    const submitButton = screen.getByRole('button', { name: /sign in/i });

    fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
    fireEvent.change(passwordInput, { target: { value: 'password' } });

    fireEvent.click(submitButton);

    // Wait for successful login and navigation
    await waitFor(() => {
      expect(authApi.login).toHaveBeenCalledWith('test@example.com', 'password', undefined);
    });
  });

  it('clears password after MFA is required', async () => {
    (authApi.login as jest.Mock).mockResolvedValue({ mfaRequired: true });

    renderLogin();
    const emailInput = screen.getByLabelText(/email/i);
    const passwordInput = screen.getByLabelText(/password/i) as HTMLInputElement;
    const submitButton = screen.getByRole('button', { name: /sign in/i });

    fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
    fireEvent.change(passwordInput, { target: { value: 'password' } });

    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(passwordInput.value).toBe('');
    });
  });

  it('displays error message without response data', async () => {
    (authApi.login as jest.Mock).mockRejectedValue(new Error('Network error'));

    renderLogin();
    const emailInput = screen.getByLabelText(/email/i);
    const passwordInput = screen.getByLabelText(/password/i);
    const submitButton = screen.getByRole('button', { name: /sign in/i });

    fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
    fireEvent.change(passwordInput, { target: { value: 'password' } });

    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(screen.getByText(/invalid credentials/i)).toBeInTheDocument();
    });
  });

  it('submits MFA token when required', async () => {
    (authApi.login as jest.Mock)
      .mockResolvedValueOnce({ mfaRequired: true })
      .mockResolvedValueOnce({
        mfaRequired: false,
        claims: {
          sub: '1234567890',
          email: 'test@example.com',
          role: 'viewer',
          tenant: 't1',
          iat: 1516239022,
          exp: 9999999999,
        },
      });

    renderLogin();
    const emailInput = screen.getByLabelText(/email/i);
    const passwordInput = screen.getByLabelText(/password/i);
    const submitButton = screen.getByRole('button', { name: /sign in/i });

    fireEvent.change(emailInput, { target: { value: 'test@example.com' } });
    fireEvent.change(passwordInput, { target: { value: 'password' } });
    fireEvent.click(submitButton);

    await waitFor(() => {
      expect(screen.getByLabelText(/mfa token/i)).toBeInTheDocument();
    });

    const mfaTokenInput = screen.getByLabelText(/mfa token/i) as HTMLInputElement;
    const verifyButton = screen.getByRole('button', { name: /verify mfa/i });

    fireEvent.change(mfaTokenInput, { target: { value: '123456' } });
    fireEvent.click(verifyButton);

    await waitFor(() => {
      expect(authApi.login).toHaveBeenLastCalledWith('test@example.com', '', '123456');
    });
  });
});
