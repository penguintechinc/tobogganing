import { useState, type FormEvent } from "react";
import { Snowflake, AlertCircle } from "lucide-react";
import { useAuth } from "../lib/auth";

export default function Login() {
  const { login } = useAuth();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);

    try {
      await login(email, password);
    } catch {
      setError("Invalid email or password. Please try again.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg-primary px-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="mb-8 text-center">
          <Snowflake className="mx-auto mb-4 h-14 w-14 text-accent" />
          <h1 className="text-3xl font-bold text-text-gold">Tobogganing</h1>
          <p className="mt-2 text-text-secondary">
            Hub Management Console
          </p>
        </div>

        {/* Login form */}
        <form
          onSubmit={handleSubmit}
          className="rounded-xl border border-border bg-bg-secondary p-8 shadow-lg"
        >
          <h2 className="mb-6 text-xl font-semibold text-text-primary">
            Sign In
          </h2>

          {error && (
            <div className="mb-4 flex items-center gap-2 rounded-lg bg-error/10 p-3 text-sm text-error">
              <AlertCircle className="h-4 w-4 shrink-0" />
              <span>{error}</span>
            </div>
          )}

          <div className="space-y-4">
            <div>
              <label
                htmlFor="email"
                className="mb-1.5 block text-sm font-medium text-text-secondary"
              >
                Email
              </label>
              <input
                id="email"
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                required
                autoComplete="email"
                placeholder="admin@example.com"
                className="w-full rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>

            <div>
              <label
                htmlFor="password"
                className="mb-1.5 block text-sm font-medium text-text-secondary"
              >
                Password
              </label>
              <input
                id="password"
                type="password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                required
                autoComplete="current-password"
                placeholder="Enter your password"
                className="w-full rounded-lg border border-border bg-bg-primary px-4 py-2.5 text-text-primary placeholder:text-text-muted focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
              />
            </div>

            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-accent py-2.5 text-sm font-semibold text-bg-primary transition-colors hover:bg-accent-hover disabled:opacity-50"
            >
              {loading ? "Signing in..." : "Sign In"}
            </button>
          </div>
        </form>

        <p className="mt-6 text-center text-xs text-text-muted">
          Powered by Penguin Tech Inc
        </p>
      </div>
    </div>
  );
}
