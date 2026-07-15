import React, { createContext, useContext, useState, ReactNode, useEffect } from 'react';
import { logout as authLogout, getStoredClaims, login as authLogin } from '../api/auth';

interface Claims {
  sub: string;
  email: string;
  role: string;
  tenant: string;
  iat: number;
  exp: number;
}

interface AuthResult {
  mfaRequired: boolean;
  claims?: Claims;
}

interface AuthContextType {
  user: Claims | null;
  isAuthenticated: boolean;
  login: (email: string, password: string, mfaToken?: string) => Promise<AuthResult>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Claims | null>(null);

  useEffect(() => {
    const storedClaims = getStoredClaims();
    if (storedClaims) {
      setUser(storedClaims);
    }
  }, []);

  const login = async (email: string, password: string, mfaToken?: string) => {
    const result = await authLogin(email, password, mfaToken);
    if (!result.mfaRequired && result.claims) {
      setUser(result.claims);
    }
    return result;
  };

  const logout = async () => {
    await authLogout();
    setUser(null);
  };

  return (
    <AuthContext.Provider value={{ user, isAuthenticated: !!user, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextType {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
}
