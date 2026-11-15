import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api, getRefreshToken, getToken, setRefreshToken, setToken } from '../api/client';
import type { User } from '../api/types';

interface AuthState {
  user: User | null;
  loading: boolean;
  ready: boolean;
}

interface AuthContextValue extends AuthState {
  login: (email: string, password: string) => Promise<void>;
  register: (input: {
    email: string;
    password: string;
    name: string;
    age_confirmed: boolean;
    accept_terms: boolean;
    invite_code?: string;
  }) => Promise<void>;
  logout: () => void;
  refreshUser: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(false);
  const [ready, setReady] = useState(false);

  const refreshUser = useCallback(async () => {
    try {
      const me = await api.me();
      setUser(me);
    } catch {
      setUser(null);
      setToken(null);
      setRefreshToken(null);
    }
  }, []);

  // On mount, restore a session if a token is present.
  useEffect(() => {
    let cancelled = false;
    (async () => {
      if (!getToken() && !getRefreshToken()) {
        setReady(true);
        return;
      }
      try {
        const me = await api.me();
        if (!cancelled) setUser(me);
      } catch {
        if (!cancelled) setUser(null);
      } finally {
        if (!cancelled) setReady(true);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    setLoading(true);
    try {
      const session = await api.login({ email, password });
      setToken(session.token);
      setRefreshToken(session.refresh_token);
      setUser(session.user);
    } finally {
      setLoading(false);
    }
  }, []);

  const register = useCallback(
    async (input: {
      email: string;
      password: string;
      name: string;
      age_confirmed: boolean;
      accept_terms: boolean;
      invite_code?: string;
    }) => {
      setLoading(true);
      try {
        const session = await api.register(input);
        setToken(session.token);
        setRefreshToken(session.refresh_token);
        setUser(session.user);
      } finally {
        setLoading(false);
      }
    },
    [],
  );

  const logout = useCallback(() => {
    setToken(null);
    setRefreshToken(null);
    setUser(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({ user, loading, ready, login, register, logout, refreshUser }),
    [user, loading, ready, login, register, logout, refreshUser],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
