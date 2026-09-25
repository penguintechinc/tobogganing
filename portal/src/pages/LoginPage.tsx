import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../context/AuthContext';

export function LoginPage() {
  const navigate = useNavigate();
  const { login } = useAuth();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [mfaToken, setMfaToken] = useState('');
  const [mfaRequired, setMfaRequired] = useState(false);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      console.log('[LoginPage] Submit { email: "u***@..." }');
      const result = await login(email, password, mfaRequired ? mfaToken : undefined);

      if (result.mfaRequired) {
        setMfaRequired(true);
        setPassword('');
      } else if (result.claims) {
        console.log('[LoginPage] Login successful');
        navigate('/');
      }
    } catch (err) {
      console.log('[LoginPage] Login error');
      const error = err as { response?: { data?: { error?: string } } };
      setError(error.response?.data?.error || 'Invalid credentials');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen bg-slate-900 flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        <div className="bg-slate-800 rounded-lg border border-slate-700 shadow-xl p-8">
          <h1 className="text-3xl font-bold text-amber-400 mb-2 text-center">Tobogganing Portal</h1>
          <p className="text-amber-600 text-center mb-8">Sign in to continue</p>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label htmlFor="email" className="block text-sm font-medium text-amber-400 mb-2">
                Email
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@example.com"
                disabled={mfaRequired}
                required
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-amber-400 placeholder-amber-600 focus:ring-2 focus:ring-sky-500 focus:outline-none disabled:opacity-50"
              />
            </div>

            <div>
              <label htmlFor="password" className="block text-sm font-medium text-amber-400 mb-2">
                Password
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                disabled={mfaRequired}
                required
                className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-amber-400 placeholder-amber-600 focus:ring-2 focus:ring-sky-500 focus:outline-none disabled:opacity-50"
              />
            </div>

            {mfaRequired && (
              <div>
                <label htmlFor="mfaToken" className="block text-sm font-medium text-amber-400 mb-2">
                  MFA Token
                </label>
                <input
                  id="mfaToken"
                  type="text"
                  value={mfaToken}
                  onChange={(e) => setMfaToken(e.target.value)}
                  placeholder="000000"
                  required
                  className="w-full px-3 py-2 bg-slate-700 border border-slate-600 rounded-lg text-amber-400 placeholder-amber-600 focus:ring-2 focus:ring-sky-500 focus:outline-none"
                />
              </div>
            )}

            {error && <p className="text-red-400 text-sm">{error}</p>}

            <button
              type="submit"
              disabled={loading}
              className="w-full px-4 py-2 bg-sky-600 hover:bg-sky-700 text-white font-medium rounded-lg transition-colors disabled:opacity-50"
            >
              {loading ? 'Signing in...' : mfaRequired ? 'Verify MFA' : 'Sign In'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
