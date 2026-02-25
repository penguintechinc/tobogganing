import {
  createContext,
  useContext,
  useState,
  useEffect,
  useCallback,
  type ReactNode,
} from "react";
import { Navigate } from "react-router-dom";
import { authApi, type User } from "./api";

const TOKEN_KEY = "tobogganing_token";

interface AuthState {
  user: User | null;
  loading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  hasScope: (scope: string) => boolean;
}

const AuthContext = createContext<AuthState | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  // Check for existing session on mount
  useEffect(() => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token) {
      authApi
        .me()
        .then((userData) => {
          setUser(userData);
        })
        .catch(() => {
          localStorage.removeItem(TOKEN_KEY);
          setUser(null);
        })
        .finally(() => {
          setLoading(false);
        });
    } else {
      setLoading(false);
    }
  }, []);

  // Token refresh timer
  useEffect(() => {
    if (!user) return;

    const refreshInterval = setInterval(
      () => {
        authApi
          .refresh()
          .then((response) => {
            localStorage.setItem(TOKEN_KEY, response.token);
            setUser(response.user);
          })
          .catch(() => {
            localStorage.removeItem(TOKEN_KEY);
            setUser(null);
          });
      },
      14 * 60 * 1000,
    ); // Refresh every 14 minutes

    return () => clearInterval(refreshInterval);
  }, [user]);

  const login = useCallback(async (email: string, password: string) => {
    const response = await authApi.login(email, password);
    localStorage.setItem(TOKEN_KEY, response.token);
    setUser(response.user);
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      localStorage.removeItem(TOKEN_KEY);
      setUser(null);
    }
  }, []);

  const hasScope = useCallback((required: string) => {
    if (!user?.scopes) return false;
    const [reqResource, reqAction] = required.split(":");
    return user.scopes.some((available) => {
      if (available === required) return true;
      const [availResource, availAction] = available.split(":");
      if (availResource === "*" && availAction === "*") return true;
      if (availResource === "*" && availAction === reqAction) return true;
      if (availResource === reqResource && availAction === "*") return true;
      return false;
    });
  }, [user]);

  if (loading) {
    return (
      <div className="flex min-h-screen items-center justify-center bg-bg-primary">
        <div className="text-center">
          <div className="mx-auto mb-4 h-8 w-8 animate-spin rounded-full border-2 border-accent border-t-transparent" />
          <p className="text-text-secondary">Loading...</p>
        </div>
      </div>
    );
  }

  return (
    <AuthContext.Provider value={{ user, loading, login, logout, hasScope }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { user, loading } = useAuth();

  if (loading) {
    return null;
  }

  if (!user) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

export function ScopeGate({
  scope,
  children,
  fallback = null,
}: {
  scope: string;
  children: ReactNode;
  fallback?: ReactNode;
}) {
  const { hasScope } = useAuth();
  return hasScope(scope) ? <>{children}</> : <>{fallback}</>;
}
