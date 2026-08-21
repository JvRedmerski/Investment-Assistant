/**
 * Who is signed in, and the two calls that change that.
 *
 * The token lives in `localStorage` so a reload does not sign the
 * investor out. That is a deliberate trade: it survives a refresh and it
 * is readable by any script that gets onto the page. For a read-only
 * research tool with no order execution the exposure is bounded, and the
 * alternative — an httpOnly cookie — needs a backend that issues one,
 * which is Wave 24's security hardening rather than this wave's.
 */

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import { ApiError, getToken, request, setToken } from '@/lib/api';
import { tokenSchema, userSchema, type User } from '@/types/api';

interface AuthState {
  user: User | null;
  /** True until the stored token has been checked against the backend. */
  loading: boolean;
  signIn: (email: string, password: string) => Promise<void>;
  register: (email: string, password: string) => Promise<void>;
  signOut: () => void;
}

const AuthContext = createContext<AuthState | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  // There is only something to verify when a token was stored, so the
  // initial value states that rather than an effect correcting it a
  // render later — which is a cascading render, and what the lint rule
  // about setState-in-effect exists to prevent.
  const [loading, setLoading] = useState(() => getToken() !== null);

  useEffect(() => {
    // A token in storage is a claim, not proof: it may have expired
    // while the tab was closed. `/auth/me` is what settles it, and until
    // it answers the app shows neither the login screen nor the
    // dashboard — flashing one and then the other is worse than waiting.
    if (!getToken()) return;
    let cancelled = false;
    request('/auth/me', userSchema)
      .then((me) => {
        if (!cancelled) setUser(me);
      })
      .catch(() => {
        if (!cancelled) setToken(null);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const authenticate = useCallback(async (email: string, password: string) => {
    const token = await request('/auth/login', tokenSchema, {
      method: 'POST',
      body: { email, password },
      anonymous: true,
    });
    setToken(token.access_token);
    setUser(await request('/auth/me', userSchema));
  }, []);

  const register = useCallback(
    async (email: string, password: string) => {
      await request('/auth/register', userSchema, {
        method: 'POST',
        body: { email, password },
        anonymous: true,
      });
      // Registering does not return a token, so the account is signed in
      // by the normal route immediately afterwards.
      await authenticate(email, password);
    },
    [authenticate],
  );

  const signOut = useCallback(() => {
    setToken(null);
    setUser(null);
  }, []);

  const value = useMemo(
    () => ({ user, loading, signIn: authenticate, register, signOut }),
    [user, loading, authenticate, register, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthState {
  const context = useContext(AuthContext);
  if (context === null) {
    throw new Error('useAuth precisa estar dentro de <AuthProvider>.');
  }
  return context;
}

/** Whether an error means the session is over rather than the request failed. */
export function isSessionExpired(error: unknown): boolean {
  return error instanceof ApiError && error.isUnauthorised;
}
