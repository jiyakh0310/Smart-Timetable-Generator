import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { api, setUnauthorizedHandler, tokenStore } from '../services/api.js';

const AuthContext = createContext(null);

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null);
  // "loading" while we check a saved token; the UI must not flash the login page meanwhile.
  const [status, setStatus] = useState(tokenStore.get() ? 'loading' : 'ready');

  const logout = useCallback(() => {
    tokenStore.clear();
    setUser(null);
    setStatus('ready');
  }, []);

  useEffect(() => {
    setUnauthorizedHandler(logout);
  }, [logout]);

  useEffect(() => {
    if (!tokenStore.get()) return;
    let cancelled = false;
    api.get('/auth/me')
      .then((profile) => { if (!cancelled) setUser(profile); })
      .catch(() => { if (!cancelled) tokenStore.clear(); })
      .finally(() => { if (!cancelled) setStatus('ready'); });
    return () => { cancelled = true; };
  }, []);

  const login = useCallback(async (email, password) => {
    const data = await api.post('/auth/login', { email, password }, { auth: false });
    tokenStore.set(data.token);
    setUser(data.user);
    return data.user;
  }, []);

  const value = useMemo(() => ({ user, status, login, logout }), [user, status, login, logout]);
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>');
  return ctx;
}
