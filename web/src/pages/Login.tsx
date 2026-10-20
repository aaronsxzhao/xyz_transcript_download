/**
 * Login/Signup page
 */
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Loader2, Radio, Mail, Lock, AlertCircle } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import { setRememberMe, getRememberMe } from '../lib/auth'

type AuthMode = 'signin' | 'signup' | 'recovery'

export default function Login() {
  const navigate = useNavigate()
  const { signIn, signUp } = useAuth()
  
  const [mode, setMode] = useState<AuthMode>('signin')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [rememberMe, setRememberMeState] = useState(getRememberMe())

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setError('')
    setMessage('')

    if (!email || (mode !== 'recovery' && !password)) {
      setError('Please fill in all fields')
      return
    }

    if (mode === 'signup' && password !== confirmPassword) {
      setError('Passwords do not match')
      return
    }

    if (mode !== 'recovery' && password.length < (mode === 'signup' ? 8 : 6)) {
      setError(`Password must be at least ${mode === 'signup' ? 8 : 6} characters`)
      return
    }

    setLoading(true)

    try {
      // Set remember me preference before signing in
      setRememberMe(rememberMe)
      
      if (mode === 'recovery') {
        const response = await fetch('/api/auth/password-reset', {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({email})})
        const result = await response.json()
        if (!response.ok) throw new Error(result.detail || 'Cannot request password recovery')
        setMessage(result.message)
      } else if (mode === 'signin') {
        await signIn(email, password)
        navigate('/')
      } else {
        const signedIn = await signUp(email, password)
        if (signedIn) navigate('/')
        else setMessage('Check your email for a confirmation link')
      }
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Authentication failed')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="min-h-screen bg-dark-bg flex items-center justify-center px-4">
      <div className="w-full max-w-md">
        {/* Logo */}
        <div className="text-center mb-8">
          <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-indigo-600 mb-4">
            <Radio className="w-8 h-8 text-white" />
          </div>
          <h1 className="text-2xl font-bold text-white">Podcast Transcript Tool</h1>
          <p className="text-gray-400 mt-2">
            {mode === 'signin' ? 'Sign in to your account' : mode === 'recovery' ? 'Recover your account' : 'Create a new account'}
          </p>
        </div>

        {/* Auth Form */}
        <div className="bg-dark-surface border border-dark-border rounded-xl p-6">
          <form onSubmit={handleSubmit} className="space-y-4">
            {/* Email */}
            <div>
              <label htmlFor="auth-email" className="block text-sm font-medium text-gray-300 mb-1">
                Email
              </label>
              <div className="relative">
                <Mail className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
                <input
                  type="email"
                  id="auth-email"
                  autoComplete="username"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="you@example.com"
                  className="w-full pl-10 pr-4 py-2.5 bg-dark-bg border border-dark-border rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                />
              </div>
            </div>

            {/* Password */}
            {mode !== 'recovery' && <div>
              <label htmlFor="auth-password" className="block text-sm font-medium text-gray-300 mb-1">
                Password
              </label>
              <div className="relative">
                <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
                <input
                  type="password"
                  id="auth-password"
                  autoComplete={mode === 'signin' ? 'current-password' : 'new-password'}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••"
                  className="w-full pl-10 pr-4 py-2.5 bg-dark-bg border border-dark-border rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                />
              </div>
            </div>

            }
            {/* Confirm Password (signup only) */}
            {mode === 'signup' && (
              <div>
                <label htmlFor="auth-confirm-password" className="block text-sm font-medium text-gray-300 mb-1">
                  Confirm Password
                </label>
                <div className="relative">
                  <Lock className="absolute left-3 top-1/2 -translate-y-1/2 w-5 h-5 text-gray-500" />
                  <input
                    type="password"
                    id="auth-confirm-password"
                    autoComplete="new-password"
                    value={confirmPassword}
                    onChange={(e) => setConfirmPassword(e.target.value)}
                    placeholder="••••••••"
                    className="w-full pl-10 pr-4 py-2.5 bg-dark-bg border border-dark-border rounded-lg text-white placeholder-gray-500 focus:outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500"
                  />
                </div>
              </div>
            )}

            {/* Remember Me (signin only) */}
            {mode === 'signin' && (
              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  id="rememberMe"
                  checked={rememberMe}
                  onChange={(e) => setRememberMeState(e.target.checked)}
                  className="w-4 h-4 rounded border-dark-border bg-dark-bg text-indigo-600 focus:ring-indigo-500 focus:ring-offset-0"
                />
                <label htmlFor="rememberMe" className="text-sm text-gray-300 cursor-pointer">
                  Remember me
                </label>
              </div>
            )}

            {/* Error Message */}
            {error && (
              <div className="flex items-center gap-2 p-3 bg-red-500/10 border border-red-500/20 rounded-lg">
                <AlertCircle className="w-5 h-5 text-red-400 flex-shrink-0" />
                <p className="text-sm text-red-400">{error}</p>
              </div>
            )}

            {/* Success Message */}
            {message && (
              <div className="p-3 bg-green-500/10 border border-green-500/20 rounded-lg">
                <p className="text-sm text-green-400">{message}</p>
              </div>
            )}

            {/* Submit Button */}
            <button
              type="submit"
              disabled={loading}
              className="w-full py-2.5 px-4 bg-indigo-600 hover:bg-indigo-700 disabled:bg-indigo-600/50 text-white font-medium rounded-lg transition-colors flex items-center justify-center gap-2"
            >
              {loading ? (
                <>
                  <Loader2 className="w-5 h-5 animate-spin" />
                  {mode === 'signin' ? 'Signing in...' : mode === 'recovery' ? 'Sending recovery link…' : 'Creating account…'}
                </>
              ) : (
                mode === 'signin' ? 'Sign In' : mode === 'recovery' ? 'Send recovery link' : 'Create Account'
              )}
            </button>
          </form>

          <button type="button" className="mt-4 text-indigo-200 underline" onClick={() => { setMode(mode === 'recovery' ? 'signin' : 'recovery'); setError(''); setMessage('') }}>{mode === 'recovery' ? 'Back to sign in' : 'Forgot password?'}</button>
          {/* Toggle Mode */}
          <div className="mt-6 text-center">
            <p className="text-gray-400">
              {mode === 'signin' ? (
                <>
                  Don't have an account?{' '}
                  <button
                    onClick={() => {
                      setMode('signup')
                      setError('')
                      setMessage('')
                    }}
                    className="text-indigo-400 hover:text-indigo-300 font-medium"
                  >
                    Sign up
                  </button>
                </>
              ) : (
                <>
                  Already have an account?{' '}
                  <button
                    onClick={() => {
                      setMode('signin')
                      setError('')
                      setMessage('')
                    }}
                    className="text-indigo-400 hover:text-indigo-300 font-medium"
                  >
                    Sign in
                  </button>
                </>
              )}
            </p>
          </div>
        </div>

        {/* Footer */}
        <p className="text-center text-gray-500 text-sm mt-6">
          Transcribe and summarize your favorite podcasts
        </p>
      </div>
    </div>
  )
}
