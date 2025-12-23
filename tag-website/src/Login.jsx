import { useState } from 'react'
import { useNavigate, useLocation, Link } from 'react-router-dom'
import { useAuth } from './AuthContext'
import './Login.css'

function Login() {
  const [email, setEmail] = useState('')
  const [code, setCode] = useState('')
  const [step, setStep] = useState('email') // 'email' or 'code'
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const [message, setMessage] = useState('')

  const { requestCode, verifyCode } = useAuth()
  const navigate = useNavigate()
  const location = useLocation()

  // Get redirect path from query params or default based on user role
  const getRedirectPath = (user) => {
    const params = new URLSearchParams(location.search)
    const redirectTo = params.get('redirect')
    if (redirectTo) return redirectTo
    return user?.is_admin ? '/admin' : '/employee'
  }

  const handleRequestCode = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const result = await requestCode(email.trim().toLowerCase())
      if (result.success) {
        setMessage(result.message)
        setStep('code')
      } else {
        setError(result.message || 'Failed to send code')
      }
    } catch (err) {
      setError('Network error. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleVerifyCode = async (e) => {
    e.preventDefault()
    setError('')
    setLoading(true)

    try {
      const result = await verifyCode(email.trim().toLowerCase(), code.trim())
      if (result.success) {
        const redirectPath = getRedirectPath(result.user)
        navigate(redirectPath, { replace: true })
      } else {
        setError(result.message || 'Invalid code')
      }
    } catch (err) {
      setError('Network error. Please try again.')
    } finally {
      setLoading(false)
    }
  }

  const handleCodeChange = (e) => {
    // Only allow digits, max 6
    const value = e.target.value.replace(/\D/g, '').slice(0, 6)
    setCode(value)
  }

  return (
    <div className="login-container">
      <div className="login-card">
        <div className="login-header">
          <Link to="/" className="login-logo">
            <img src="/assets/logo.svg" alt="TAG Parking" />
          </Link>
          <h1>Staff Login</h1>
        </div>

        <div className="login-body">
        {step === 'email' ? (
          <form onSubmit={handleRequestCode}>
            <p className="login-instructions">
              Enter your work email address and we'll send you a login code.
            </p>
            <div className="login-field">
              <label htmlFor="email">Email Address</label>
              <input
                type="email"
                id="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@tagparking.co.uk"
                required
                autoFocus
                disabled={loading}
              />
            </div>
            {error && <div className="login-error">{error}</div>}
            <button
              type="submit"
              className="login-button"
              disabled={loading || !email.trim()}
            >
              {loading ? 'Sending...' : 'Send Login Code'}
            </button>
          </form>
        ) : (
          <form onSubmit={handleVerifyCode}>
            <p className="login-instructions">
              We've sent a 6-digit code to <strong>{email}</strong>
            </p>
            {message && <div className="login-message">{message}</div>}
            <div className="login-field">
              <label htmlFor="code">Login Code</label>
              <input
                type="text"
                id="code"
                value={code}
                onChange={handleCodeChange}
                placeholder="000000"
                required
                autoFocus
                disabled={loading}
                className="code-input"
                inputMode="numeric"
                autoComplete="one-time-code"
              />
            </div>
            {error && <div className="login-error">{error}</div>}
            <button
              type="submit"
              className="login-button"
              disabled={loading || code.length !== 6}
            >
              {loading ? 'Verifying...' : 'Login'}
            </button>
            <button
              type="button"
              className="login-back"
              onClick={() => {
                setStep('email')
                setCode('')
                setError('')
                setMessage('')
              }}
              disabled={loading}
            >
              Use a different email
            </button>
          </form>
        )}
        </div>
      </div>
    </div>
  )
}

export default Login
