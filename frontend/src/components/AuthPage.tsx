import { useState } from 'react'
import type { FormEvent } from 'react'
import { useAuth } from '@/lib/useAuth'
import { forgotPassword } from '@/lib/api'

type Mode = 'login' | 'register' | 'forgot'

function friendlyError(mode: Mode, message: string): string {
  if (mode === 'forgot') return 'Could not send a reset link. Please try again.'
  if (message.startsWith('401')) return 'Incorrect email or password.'
  if (message.startsWith('409')) return 'An account with that email already exists.'
  if (message.startsWith('422')) return 'Password must be at least 8 characters.'
  return mode === 'login' ? 'Could not sign in. Please try again.' : 'Could not create your account.'
}

interface Props {
  initialMode?: Mode
  onBack?: () => void
}

export function AuthPage({ initialMode = 'login', onBack }: Props) {
  const [mode, setMode] = useState<Mode>(initialMode)
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [forgotSubmitted, setForgotSubmitted] = useState(false)
  const { login, register } = useAuth()

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setFormError(null)
    setSubmitting(true)
    try {
      if (mode === 'login') await login(email, password)
      else if (mode === 'register') await register(email, password)
      else {
        await forgotPassword(email)
        setForgotSubmitted(true)
      }
    } catch (err) {
      setFormError(friendlyError(mode, err instanceof Error ? err.message : String(err)))
    } finally {
      setSubmitting(false)
    }
  }

  function toggleMode() {
    setMode((m) => (m === 'login' ? 'register' : 'login'))
    setFormError(null)
  }

  function showForgotPassword() {
    setMode('forgot')
    setFormError(null)
    setForgotSubmitted(false)
  }

  function backToLogin() {
    setMode('login')
    setFormError(null)
    setForgotSubmitted(false)
  }

  return (
    <div className="relative flex h-full flex-col items-center justify-center bg-paper px-4 font-sans dark:bg-paper-dark">
      {onBack && (
        <button
          type="button"
          onClick={onBack}
          className="absolute left-4 top-4 font-mono text-[11px] text-ink-muted transition-colors hover:text-ink dark:text-ink-muted-dark dark:hover:text-ink-dark"
        >
          ← Back
        </button>
      )}

      <div className="mb-6 flex items-center gap-2">
        <span className="flex h-7 w-7 items-center justify-center rounded bg-ink text-xs font-bold text-paper dark:bg-ink-dark dark:text-paper-dark">
          W
        </span>
        <span className="font-mono text-sm font-semibold tracking-wide text-ink dark:text-ink-dark">
          WAYPOINT
        </span>
      </div>

      <div className="w-full max-w-sm rounded-xl border border-line bg-surface p-6 shadow-sm dark:border-line-dark dark:bg-surface-dark">
        <h1 className="text-sm font-semibold text-ink dark:text-ink-dark">
          {mode === 'login' ? 'Sign in' : mode === 'register' ? 'Create your account' : 'Reset your password'}
        </h1>
        <p className="mt-1 text-[11px] text-ink-muted dark:text-ink-muted-dark">
          {mode === 'login'
            ? 'Sign in to continue planning your trips.'
            : mode === 'register'
              ? 'Create an account to start planning trips.'
              : "Enter your account's email and we'll send you a reset link."}
        </p>

        {mode === 'forgot' && forgotSubmitted ? (
          <div className="mt-5 space-y-4">
            <p className="rounded-md bg-accent-soft px-3 py-2 text-[11px] text-accent dark:bg-accent-soft-dark dark:text-accent-dark">
              If that email is registered, a reset link has been sent.
            </p>
            <button
              type="button"
              onClick={backToLogin}
              className="w-full rounded-lg bg-accent px-3.5 py-2 font-mono text-xs font-medium text-white transition-opacity hover:opacity-90 dark:bg-accent-dark dark:text-paper-dark"
            >
              Back to sign in
            </button>
          </div>
        ) : (
          <form className="mt-5 space-y-3" onSubmit={handleSubmit}>
            <div>
              <label
                htmlFor="email"
                className="mb-1 block font-mono text-[11px] text-ink-muted dark:text-ink-muted-dark"
              >
                Email
              </label>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg border border-line bg-paper px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none dark:border-line-dark dark:bg-paper-dark dark:text-ink-dark dark:placeholder:text-ink-faint-dark dark:focus:border-accent-dark dark:focus:ring-accent-dark"
                placeholder="you@example.com"
              />
            </div>

            {mode !== 'forgot' && (
              <div>
                <div className="mb-1 flex items-center justify-between">
                  <label
                    htmlFor="password"
                    className="block font-mono text-[11px] text-ink-muted dark:text-ink-muted-dark"
                  >
                    Password
                  </label>
                  {mode === 'login' && (
                    <button
                      type="button"
                      onClick={showForgotPassword}
                      className="font-mono text-[11px] text-ink-muted transition-colors hover:text-ink dark:text-ink-muted-dark dark:hover:text-ink-dark"
                    >
                      Forgot password?
                    </button>
                  )}
                </div>
                <input
                  id="password"
                  type="password"
                  autoComplete={mode === 'login' ? 'current-password' : 'new-password'}
                  required
                  minLength={mode === 'register' ? 8 : undefined}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full rounded-lg border border-line bg-paper px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none dark:border-line-dark dark:bg-paper-dark dark:text-ink-dark dark:placeholder:text-ink-faint-dark dark:focus:border-accent-dark dark:focus:ring-accent-dark"
                  placeholder={mode === 'register' ? 'At least 8 characters' : '••••••••'}
                />
              </div>
            )}

            {formError && (
              <p className="rounded-md bg-red-50 px-2.5 py-1.5 text-[11px] text-red-700 dark:bg-red-950/40 dark:text-red-400">
                {formError}
              </p>
            )}

            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded-lg bg-accent px-3.5 py-2 font-mono text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-accent-dark dark:text-paper-dark"
            >
              {submitting
                ? 'Please wait…'
                : mode === 'login'
                  ? 'Sign in'
                  : mode === 'register'
                    ? 'Create account'
                    : 'Send reset link'}
            </button>

            {mode === 'forgot' && (
              <button
                type="button"
                onClick={backToLogin}
                className="w-full text-center font-mono text-[11px] text-ink-muted transition-colors hover:text-ink dark:text-ink-muted-dark dark:hover:text-ink-dark"
              >
                Back to sign in
              </button>
            )}
          </form>
        )}

        {mode !== 'forgot' && (
          <button
            type="button"
            onClick={toggleMode}
            className="mt-4 w-full text-center font-mono text-[11px] text-ink-muted transition-colors hover:text-ink dark:text-ink-muted-dark dark:hover:text-ink-dark"
          >
            {mode === 'login' ? "Don't have an account? Register" : 'Already have an account? Sign in'}
          </button>
        )}
      </div>
    </div>
  )
}
