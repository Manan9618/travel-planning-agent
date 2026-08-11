import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'
import {
  getAuthToken,
  setAuthToken,
  login as apiLogin,
  register as apiRegister,
  getCurrentUser,
} from '@/lib/api'
import type { UserResponse } from '@/types/api'

interface AuthContextValue {
  user: UserResponse | null
  loading: boolean
  error: string | null
  login: (email: string, password: string) => Promise<void>
  register: (email: string, password: string) => Promise<void>
  loginWithToken: (token: string) => Promise<void>
  logout: () => void
}

const AuthContext = createContext<AuthContextValue | null>(null)

// Multiple places (the auth gate, a header logout button, login/register
// forms) all need the *same* current-user state, not independent copies —
// unlike useTheme (one consumer), this needs a Provider so every useAuth()
// call shares one source of truth.
export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!getAuthToken()) {
      setLoading(false)
      return
    }
    getCurrentUser()
      .then(setUser)
      .catch(() => setAuthToken(null)) // stored token is stale/invalid - drop it
      .finally(() => setLoading(false))
  }, [])

  async function login(email: string, password: string) {
    setError(null)
    try {
      const res = await apiLogin(email, password)
      setAuthToken(res.access_token)
      setUser({ user_id: res.user_id, email: res.email })
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      throw err
    }
  }

  async function register(email: string, password: string) {
    setError(null)
    try {
      const res = await apiRegister(email, password)
      setAuthToken(res.access_token)
      setUser({ user_id: res.user_id, email: res.email })
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      throw err
    }
  }

  // Google sign-in already produced a real bearer token server-side (see
  // App.tsx's `?oauth_token=` handling) — this just adopts it the same way
  // the initial-mount effect above does for a token found in localStorage,
  // rather than duplicating that fetch-user-then-setUser logic a third time.
  async function loginWithToken(token: string) {
    setError(null)
    setAuthToken(token)
    try {
      const me = await getCurrentUser()
      setUser(me)
    } catch (err) {
      setAuthToken(null)
      setError(err instanceof Error ? err.message : String(err))
      throw err
    }
  }

  function logout() {
    setAuthToken(null)
    setUser(null)
  }

  return (
    <AuthContext.Provider
      value={{ user, loading, error, login, register, loginWithToken, logout }}
    >
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext)
  if (!ctx) throw new Error('useAuth must be used within an AuthProvider')
  return ctx
}
