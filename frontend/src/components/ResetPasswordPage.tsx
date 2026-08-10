import { useState } from 'react'
import type { FormEvent } from 'react'
import { resetPassword } from '@/lib/api'

interface Props {
  token: string
  onDone: () => void
}

function friendlyResetError(message: string): string {
  if (message.startsWith('400')) return 'This reset link is invalid or has expired. Request a new one.'
  if (message.startsWith('422')) return 'Password must be at least 8 characters.'
  return 'Could not reset your password. Please try again.'
}

export function ResetPasswordPage({ token, onDone }: Props) {
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    if (password !== confirm) {
      setError('Passwords do not match.')
      return
    }
    setSubmitting(true)
    try {
      await resetPassword(token, password)
      setSuccess(true)
    } catch (err) {
      setError(friendlyResetError(err instanceof Error ? err.message : String(err)))
    } finally {
      setSubmitting(false)
    }
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
        {success ? (
          <>
            <h1 className="text-sm font-semibold text-ink dark:text-ink-dark">Password updated</h1>
            <p className="mt-1 text-[11px] text-ink-muted dark:text-ink-muted-dark">
              You can now sign in with your new password.
            </p>
            <button
              type="button"
              onClick={onDone}
              className="mt-5 w-full rounded-lg bg-accent px-3.5 py-2 font-mono text-xs font-medium text-white transition-opacity hover:opacity-90 dark:bg-accent-dark dark:text-paper-dark"
            >
              Go to sign in
            </button>
          </>
        ) : (
          <>
            <h1 className="text-sm font-semibold text-ink dark:text-ink-dark">Set a new password</h1>
            <p className="mt-1 text-[11px] text-ink-muted dark:text-ink-muted-dark">
              Choose a new password for your account.
            </p>

            <form className="mt-5 space-y-3" onSubmit={handleSubmit}>
              <div>
                <label
                  htmlFor="new-password"
                  className="mb-1 block font-mono text-[11px] text-ink-muted dark:text-ink-muted-dark"
                >
                  New password
                </label>
                <input
                  id="new-password"
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={8}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className="w-full rounded-lg border border-line bg-paper px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none dark:border-line-dark dark:bg-paper-dark dark:text-ink-dark dark:placeholder:text-ink-faint-dark dark:focus:border-accent-dark dark:focus:ring-accent-dark"
                  placeholder="At least 8 characters"
                />
              </div>

              <div>
                <label
                  htmlFor="confirm-password"
                  className="mb-1 block font-mono text-[11px] text-ink-muted dark:text-ink-muted-dark"
                >
                  Confirm password
                </label>
                <input
                  id="confirm-password"
                  type="password"
                  autoComplete="new-password"
                  required
                  minLength={8}
                  value={confirm}
                  onChange={(e) => setConfirm(e.target.value)}
                  className="w-full rounded-lg border border-line bg-paper px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-accent focus:ring-1 focus:ring-accent focus:outline-none dark:border-line-dark dark:bg-paper-dark dark:text-ink-dark dark:placeholder:text-ink-faint-dark dark:focus:border-accent-dark dark:focus:ring-accent-dark"
                  placeholder="Re-enter your new password"
                />
              </div>

              {error && (
                <p className="rounded-md bg-red-50 px-2.5 py-1.5 text-[11px] text-red-700 dark:bg-red-950/40 dark:text-red-400">
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={submitting}
                className="w-full rounded-lg bg-accent px-3.5 py-2 font-mono text-xs font-medium text-white transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-accent-dark dark:text-paper-dark"
              >
                {submitting ? 'Please wait…' : 'Reset password'}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  )
}
