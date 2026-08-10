import { useEffect, useState } from 'react'
import { deleteSession, listSessions } from '@/lib/api'
import type { SessionSummary } from '@/types/api'

interface Props {
  onSelect: (session: SessionSummary) => void
  onNewTrip: () => void
}

function formatRelative(iso: string): string {
  const date = new Date(iso)
  const diffDays = Math.floor((Date.now() - date.getTime()) / (1000 * 60 * 60 * 24))
  if (diffDays <= 0) return 'Today'
  if (diffDays === 1) return 'Yesterday'
  if (diffDays < 30) return `${diffDays} days ago`
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric', year: 'numeric' })
}

const STATUS_LABELS: Record<string, string> = {
  completed: 'Completed',
  running: 'In progress',
  awaiting_review: 'Needs review',
  failed: 'Failed',
}

export function Dashboard({ onSelect, onNewTrip }: Props) {
  const [sessions, setSessions] = useState<SessionSummary[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [confirmingId, setConfirmingId] = useState<string | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    listSessions()
      .then((res) => {
        if (!cancelled) setSessions(res.sessions)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      })
    return () => {
      cancelled = true
    }
  }, [])

  async function handleDelete(sessionId: string) {
    setDeletingId(sessionId)
    setError(null)
    try {
      await deleteSession(sessionId)
      setSessions((prev) => (prev ?? []).filter((s) => s.session_id !== sessionId))
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setDeletingId(null)
      setConfirmingId(null)
    }
  }

  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-y-auto bg-paper dark:bg-paper-dark">
      <div className="mx-auto w-full max-w-2xl flex-1 px-4 py-10">
        <div className="mb-6 flex items-center justify-between">
          <h1 className="text-xl font-semibold text-ink dark:text-ink-dark">My Trips</h1>
          <button
            type="button"
            onClick={onNewTrip}
            className="rounded-lg bg-accent px-3.5 py-2 font-mono text-xs font-medium text-white transition-opacity hover:opacity-90 dark:bg-accent-dark dark:text-paper-dark"
          >
            + New trip
          </button>
        </div>

        {error && (
          <p className="mb-4 rounded-md bg-red-50 px-3 py-2 text-sm text-red-700 dark:bg-red-950/40 dark:text-red-400">
            {error}
          </p>
        )}

        {sessions === null && !error && (
          <p className="font-mono text-xs text-ink-faint dark:text-ink-faint-dark">
            Loading your trips…
          </p>
        )}

        {sessions !== null && sessions.length === 0 && (
          <div className="rounded-xl border border-dashed border-line p-8 text-center dark:border-line-dark">
            <p className="text-sm text-ink-muted dark:text-ink-muted-dark">
              No trips yet — describe where you want to go and Waypoint will plan it.
            </p>
            <button
              type="button"
              onClick={onNewTrip}
              className="mt-4 rounded-lg bg-accent px-3.5 py-2 font-mono text-xs font-medium text-white transition-opacity hover:opacity-90 dark:bg-accent-dark dark:text-paper-dark"
            >
              Plan your first trip
            </button>
          </div>
        )}

        {sessions !== null && sessions.length > 0 && (
          <ul className="animate-fade-in space-y-2">
            {sessions.map((s) => (
              <li
                key={s.session_id}
                className="flex items-center gap-2 rounded-xl border border-line bg-surface p-4 transition-colors hover:border-accent dark:border-line-dark dark:bg-surface-dark dark:hover:border-accent-dark"
              >
                <button
                  type="button"
                  onClick={() => onSelect(s)}
                  className="min-w-0 flex-1 text-left"
                >
                  <p className="truncate text-sm font-medium text-ink dark:text-ink-dark">
                    {s.raw_text}
                  </p>
                  <p className="mt-1 font-mono text-[11px] text-ink-faint dark:text-ink-faint-dark">
                    {formatRelative(s.created_at)}
                  </p>
                </button>

                <span className="shrink-0 rounded-full bg-accent-soft px-2 py-0.5 font-mono text-[10px] font-medium text-accent dark:bg-accent-soft-dark dark:text-accent-dark">
                  {STATUS_LABELS[s.status] ?? s.status}
                </span>

                {confirmingId === s.session_id ? (
                  <div className="flex shrink-0 items-center gap-1">
                    <button
                      type="button"
                      disabled={deletingId === s.session_id}
                      onClick={() => handleDelete(s.session_id)}
                      className="rounded-md bg-red-600 px-2 py-1 font-mono text-[10px] font-medium text-white transition-opacity hover:opacity-90 disabled:opacity-50"
                    >
                      {deletingId === s.session_id ? 'Deleting…' : 'Delete'}
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirmingId(null)}
                      className="rounded-md border border-line px-2 py-1 font-mono text-[10px] text-ink-muted transition-colors hover:text-ink dark:border-line-dark dark:text-ink-muted-dark dark:hover:text-ink-dark"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <button
                    type="button"
                    onClick={() => setConfirmingId(s.session_id)}
                    aria-label={`Delete trip: ${s.raw_text}`}
                    title="Delete trip"
                    className="shrink-0 rounded-md px-2 py-1 font-mono text-[11px] text-ink-faint transition-colors hover:text-red-600 dark:text-ink-faint-dark dark:hover:text-red-400"
                  >
                    ✕
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  )
}
