import { createContext, useContext, useState, useEffect } from 'react'

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

  const value = {
    user,
    token,
    loading,
    isAuthenticated: !!user,
    isAdmin: user?.is_admin || false,
    requestCode,
    verifyCode,
    logout,
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
