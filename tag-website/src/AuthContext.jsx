import { createContext, useCallback, useContext, useState, useEffect } from 'react'

const AuthContext = createContext(null)

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export function AuthProvider({ children }) {
  const [user, setUser] = useState(() => {
    const cached = localStorage.getItem('auth_user')
    if (!cached) return null
    try {
      return JSON.parse(cached)
    } catch {
      localStorage.removeItem('auth_user')
      return null
    }
  })
  const [token, setToken] = useState(() => localStorage.getItem('auth_token'))
  const [loading, setLoading] = useState(true)

  const clearAuth = useCallback(() => {
    localStorage.removeItem('auth_token')
    localStorage.removeItem('auth_user')
    setToken(null)
    setUser(null)
  }, [])

  // Check session on mount
  useEffect(() => {
    if (token) {
      checkSession()
    } else {
      setLoading(false)
    }
  }, [])

  const checkSession = async () => {
    const checkedToken = token
    try {
      const response = await fetch(`${API_URL}/api/auth/me`, {
        headers: {
          'Authorization': `Bearer ${checkedToken}`,
        },
      })
      if (response.ok) {
        const userData = await response.json()
        localStorage.setItem('auth_user', JSON.stringify(userData))
        setUser(userData)
      } else if (response.status === 401 || response.status === 403) {
        if (localStorage.getItem('auth_token') === checkedToken) {
          clearAuth()
        }
      } else {
        // Transient backend/deploy errors must not destroy a valid 24-hour session.
        console.warn('Session check returned non-auth error:', response.status)
      }
    } catch (error) {
      console.error('Session check error:', error)
      // Network errors are not proof that the token expired. Keep cached auth so
      // a short deploy/restart blip does not kick admins out.
    } finally {
      setLoading(false)
    }
  }

  const requestCode = async (email) => {
    const response = await fetch(`${API_URL}/api/auth/request-code`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email }),
    })
    return response.json()
  }

  const verifyCode = async (email, code) => {
    const response = await fetch(`${API_URL}/api/auth/verify-code`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ email, code }),
    })
    const data = await response.json()

    if (data.success && data.token) {
      localStorage.setItem('auth_token', data.token)
      localStorage.setItem('auth_user', JSON.stringify(data.user))
      setToken(data.token)
      setUser(data.user)
    }

    return data
  }

  const logout = async () => {
    if (token) {
      try {
        await fetch(`${API_URL}/api/auth/logout`, {
          method: 'POST',
          headers: {
            'Authorization': `Bearer ${token}`,
          },
        })
      } catch (error) {
        console.error('Logout error:', error)
      }
    }

    clearAuth()
  }

  // Drop-in replacement for `fetch` that:
  //   1. Auto-attaches the current Bearer token (if any) when no Authorization
  //      header is already set by the caller.
  //   2. On 401 from any logged-in call, clears the local auth state. The
  //      consumer's existing "redirect when !isAuthenticated" effect (see
  //      Employee.jsx and Admin.jsx) then bounces the user to /login.
  //
  // Use this everywhere a session-protected endpoint is called. Public
  // endpoints can keep using bare `fetch`.
  const authFetch = useCallback(async (input, init = {}) => {
    const headers = new Headers(init.headers || {})
    if (token && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${token}`)
    }
    const response = await fetch(input, { ...init, headers })
    if (response.status === 401 && token && localStorage.getItem('auth_token') === token) {
      // Server says this token is dead (user deleted, session expired,
      // session revoked). Tear down local state synchronously — the
      // consumer's isAuthenticated effect will handle the redirect on
      // the next React render.
      clearAuth()
    }
    return response
  }, [token, clearAuth])

  const value = {
    user,
    token,
    loading,
    isAuthenticated: !!user,
    isAdmin: user?.is_admin || false,
    requestCode,
    verifyCode,
    logout,
    authFetch,
  }

  return (
    <AuthContext.Provider value={value}>
      {children}
    </AuthContext.Provider>
  )
}

export function useAuth() {
  const context = useContext(AuthContext)
  if (!context) {
    throw new Error('useAuth must be used within an AuthProvider')
  }
  return context
}
