import { useState } from 'react'
import type { FormEvent } from 'react'
import { useAuth } from '@/lib/useAuth'

type Mode = 'login' | 'register'

function friendlyError(mode: Mode, message: string): string {
  if (message.startsWith('401')) return 'Incorrect email or password.'
  if (message.startsWith('409')) return 'An account with that email already exists.'
  if (message.startsWith('422')) return 'Password must be at least 8 characters.'
  return mode === 'login' ? 'Could not sign in. Please try again.' : 'Could not create your account.'
}

export function AuthPage() {
  const [mode, setMode] = useState<Mode>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const { login, register } = useAuth()

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setFormError(null)
    setSubmitting(true)
    try {
      if (mode === 'login') await login(email, password)
      else await register(email, password)
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

  return (
    <div className="flex h-full flex-col items-center justify-center bg-paper px-4 font-sans dark:bg-paper-dark">
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
          {mode === 'login' ? 'Sign in' : 'Create your account'}
        </h1>
        <p className="mt-1 text-[11px] text-ink-muted dark:text-ink-muted-dark">
          {mode === 'login'
            ? 'Sign in to continue planning your trips.'
            : 'Create an account to start planning trips.'}
        </p>

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

          <div>
            <label
              htmlFor="password"
              className="mb-1 block font-mono text-[11px] text-ink-muted dark:text-ink-muted-dark"
            >
              Password
            </label>
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

          {formError && (
            <p className="rounded-md bg-red-50 px-2.5 py-1.5 text-[11px] text-red-700 dark:bg-red-950/40 dark:text-red-400">
              {formError}
            </p>
          )}

          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-lg bg-accent px-3.5 py-2 font-mono text-xs font-medium text-white hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-accent-dark dark:text-paper-dark"
          >
            {submitting ? 'Please wait…' : mode === 'login' ? 'Sign in' : 'Create account'}
          </button>
        </form>

        <button
          type="button"
          onClick={toggleMode}
          className="mt-4 w-full text-center font-mono text-[11px] text-ink-muted hover:text-ink dark:text-ink-muted-dark dark:hover:text-ink-dark"
        >
          {mode === 'login' ? "Don't have an account? Register" : 'Already have an account? Sign in'}
        </button>
      </div>
    </div>
  )
}
