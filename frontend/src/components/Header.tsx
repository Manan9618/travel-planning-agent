import type { Itinerary } from '@/types/api'
import { ThemeToggle } from '@/components/ThemeToggle'

interface Props {
  itinerary: Itinerary | null
  onNewTrip: () => void
  onDownloadPdf: () => void
  pdfAvailable: boolean
  hasTurns: boolean
  userEmail: string
  onLogout: () => void
}

function formatDateRange(start: string | null, end: string | null): string {
  if (!start) return ''
  const s = new Date(start)
  const startStr = s.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
  if (!end) return startStr
  const e = new Date(end)
  const endStr = e.toLocaleDateString(undefined, {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
  return `${startStr.toUpperCase()} – ${endStr.toUpperCase()}`
}

export function Header({
  itinerary,
  onNewTrip,
  onDownloadPdf,
  pdfAvailable,
  hasTurns,
  userEmail,
  onLogout,
}: Props) {
  const prefs = itinerary?.preferences
  const spent = itinerary
    ? itinerary.days
        .flatMap((d) => d.items)
        .reduce((sum, i) => sum + (i.cost ?? 0), 0) +
      (itinerary.hotel ? itinerary.hotel.price_per_night * Math.max(itinerary.days.length - 1, 1) : 0)
    : 0
  const budget = prefs?.budget_total ?? null
  const pct = budget ? Math.min(100, Math.round((spent / budget) * 100)) : null

  return (
    <header className="flex items-center gap-4 border-b border-line bg-surface px-4 py-2.5 dark:border-line-dark dark:bg-surface-dark">
      <div className="flex items-center gap-2">
        <span className="flex h-6 w-6 items-center justify-center rounded bg-ink text-[10px] font-bold text-paper dark:bg-ink-dark dark:text-paper-dark">
          W
        </span>
        <span className="font-mono text-xs font-semibold tracking-wide text-ink dark:text-ink-dark">
          WAYPOINT
        </span>
      </div>

      <div className="min-w-0 flex-1">
        {prefs ? (
          <div className="flex items-baseline gap-2 truncate">
            <h1 className="truncate text-sm font-semibold text-ink dark:text-ink-dark">
              {prefs.destination}
              {itinerary && itinerary.days.length > 0
                ? ` — ${itinerary.days.length} day${itinerary.days.length !== 1 ? 's' : ''}`
                : ''}
            </h1>
            <span className="hidden shrink-0 font-mono text-[11px] text-ink-faint sm:inline dark:text-ink-faint-dark">
              {formatDateRange(prefs.start_date, prefs.end_date)}
              {prefs.trip_style ? ` · ${prefs.trip_style.toUpperCase()}` : ''}
            </span>
          </div>
        ) : (
          <div>
            <h1 className="text-sm font-semibold text-ink dark:text-ink-dark">
              AI Travel Planning Agent
            </h1>
            <p className="text-[11px] text-ink-muted dark:text-ink-muted-dark">
              Describe a trip and I&apos;ll plan it end to end
            </p>
          </div>
        )}
      </div>

      {budget != null && pct != null && (
        <div className="hidden items-center gap-2 md:flex" title={`$${spent.toFixed(0)} of $${budget.toFixed(0)}`}>
          <span className="font-mono text-xs tabular-nums text-ink dark:text-ink-dark">
            ${spent.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            <span className="text-ink-faint dark:text-ink-faint-dark">
              /${budget.toLocaleString(undefined, { maximumFractionDigits: 0 })}
            </span>
          </span>
          <div className="h-1.5 w-20 overflow-hidden rounded-full bg-line dark:bg-line-dark">
            <div
              className="h-full bg-accent dark:bg-accent-dark"
              style={{ width: `${pct}%` }}
            />
          </div>
        </div>
      )}

      <div className="flex shrink-0 items-center gap-1.5">
        {hasTurns && (
          <button
            type="button"
            onClick={onNewTrip}
            className="rounded-md px-2 py-1 font-mono text-[11px] text-ink-muted hover:bg-paper dark:text-ink-muted-dark dark:hover:bg-paper-dark"
          >
            New trip
          </button>
        )}
        {itinerary && (
          <button
            type="button"
            onClick={onDownloadPdf}
            disabled={!pdfAvailable}
            className="rounded-md bg-ink px-2.5 py-1 font-mono text-[11px] font-medium text-paper hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-ink-dark dark:text-paper-dark"
          >
            Export PDF
          </button>
        )}
        <ThemeToggle />
        <button
          type="button"
          onClick={onLogout}
          title={userEmail}
          className="rounded-md px-2 py-1 font-mono text-[11px] text-ink-muted hover:bg-paper dark:text-ink-muted-dark dark:hover:bg-paper-dark"
        >
          Log out
        </button>
      </div>
    </header>
  )
}
