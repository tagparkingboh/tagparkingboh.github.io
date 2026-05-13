import { createContext, useCallback, useContext, useState, useEffect } from 'react'

const AuthContext = createContext(null)

const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000'

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [token, setToken] = useState(() => localStorage.getItem('auth_token'))
  const [loading, setLoading] = useState(true)

  // Check session on mount
  useEffect(() => {
    if (token) {
      checkSession()
    } else {
      setLoading(false)
    }
  }, [])

  const checkSession = async () => {
    try {
      const response = await fetch(`${API_URL}/api/auth/me`, {
        headers: {
          'Authorization': `Bearer ${token}`,
        },
      })
      if (response.ok) {
        const userData = await response.json()
        setUser(userData)
      } else {
        // Invalid session - clear token
        localStorage.removeItem('auth_token')
        setToken(null)
        setUser(null)
      }
    } catch (error) {
      console.error('Session check error:', error)
      localStorage.removeItem('auth_token')
      setToken(null)
      setUser(null)
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

    localStorage.removeItem('auth_token')
    setToken(null)
    setUser(null)
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
    if (response.status === 401 && token) {
      // Server says this token is dead (user deleted, session expired,
      // session revoked). Tear down local state synchronously — the
      // consumer's isAuthenticated effect will handle the redirect on
      // the next React render.
      localStorage.removeItem('auth_token')
      setToken(null)
      setUser(null)
    }
    return response
  }, [token])

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
