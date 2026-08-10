import { useState } from 'react'
import type { BudgetEvaluation, Itinerary } from '@/types/api'
import { formatCurrency } from '@/lib/currency'
import { destinationLabel } from '@/lib/destinations'
import { createShareLink } from '@/lib/api'
import { ThemeToggle } from '@/components/ThemeToggle'

interface Props {
  itinerary: Itinerary | null
  budgetEvaluation: BudgetEvaluation | null
  sessionId: string | null
  onNewTrip: () => void
  onDownloadPdf: () => void
  onDownloadCalendar: () => void
  onMyTrips: () => void
  pdfAvailable: boolean
  hasTurns: boolean
  userEmail: string
  onLogout: () => void
}

type ShareStatus = 'idle' | 'sharing' | 'copied' | 'error'
const SHARE_STATUS_RESET_MS = 2000

const SHARE_BUTTON_LABELS: Record<ShareStatus, string> = {
  idle: 'Share',
  sharing: 'Sharing…',
  copied: 'Link copied!',
  error: 'Could not share',
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
  budgetEvaluation,
  sessionId,
  onNewTrip,
  onDownloadPdf,
  onDownloadCalendar,
  onMyTrips,
  pdfAvailable,
  hasTurns,
  userEmail,
  onLogout,
}: Props) {
  const [shareStatus, setShareStatus] = useState<ShareStatus>('idle')
  const prefs = itinerary?.preferences

  async function handleShare() {
    if (!sessionId) return
    setShareStatus('sharing')
    try {
      const { share_url } = await createShareLink(sessionId)
      await navigator.clipboard.writeText(share_url)
      setShareStatus('copied')
    } catch {
      setShareStatus('error')
    } finally {
      setTimeout(() => setShareStatus('idle'), SHARE_STATUS_RESET_MS)
    }
  }
  // budgetEvaluation's totals are already currency-converted
  // (BudgetOptimizer.evaluate, backend) — prefer them once available.
  // Before that (or if no budget was stated at all), fall back to a raw
  // sum of line-item costs, which are always USD; the currency shown for
  // that fallback is therefore always USD too, not budget_currency.
  const usingEvaluation = budgetEvaluation != null
  const spent = usingEvaluation
    ? budgetEvaluation.total_actual
    : itinerary
      ? itinerary.days.flatMap((d) => d.items).reduce((sum, i) => sum + (i.cost ?? 0), 0) +
        (itinerary.hotel
          ? itinerary.hotel.price_per_night * Math.max(itinerary.days.length - 1, 1)
          : 0)
      : 0
  const budget = usingEvaluation ? budgetEvaluation.total_allocated : (prefs?.budget_total ?? null)
  const currency = usingEvaluation ? (prefs?.budget_currency ?? 'USD') : 'USD'
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
              {destinationLabel(prefs)}
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
        <div
          className="hidden items-center gap-2 md:flex"
          title={`${formatCurrency(spent, currency)} of ${formatCurrency(budget, currency)}`}
        >
          <span className="font-mono text-xs tabular-nums text-ink dark:text-ink-dark">
            {formatCurrency(spent, currency)}
            <span className="text-ink-faint dark:text-ink-faint-dark">
              /{formatCurrency(budget, currency)}
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
        <button
          type="button"
          onClick={onMyTrips}
          className="rounded-md px-2 py-1 font-mono text-[11px] text-ink-muted transition-colors hover:bg-paper dark:text-ink-muted-dark dark:hover:bg-paper-dark"
        >
          My Trips
        </button>
        {hasTurns && (
          <button
            type="button"
            onClick={onNewTrip}
            className="rounded-md px-2 py-1 font-mono text-[11px] text-ink-muted transition-colors hover:bg-paper dark:text-ink-muted-dark dark:hover:bg-paper-dark"
          >
            New trip
          </button>
        )}
        {itinerary && (
          <button
            type="button"
            onClick={onDownloadCalendar}
            className="rounded-md px-2 py-1 font-mono text-[11px] text-ink-muted transition-colors hover:bg-paper dark:text-ink-muted-dark dark:hover:bg-paper-dark"
          >
            Add to Calendar
          </button>
        )}
        {itinerary && (
          <button
            type="button"
            onClick={handleShare}
            disabled={shareStatus === 'sharing'}
            className="rounded-md px-2 py-1 font-mono text-[11px] text-ink-muted transition-colors hover:bg-paper disabled:cursor-not-allowed disabled:opacity-60 dark:text-ink-muted-dark dark:hover:bg-paper-dark"
          >
            {SHARE_BUTTON_LABELS[shareStatus]}
          </button>
        )}
        {itinerary && (
          <button
            type="button"
            onClick={onDownloadPdf}
            disabled={!pdfAvailable}
            className="rounded-md bg-ink px-2.5 py-1 font-mono text-[11px] font-medium text-paper transition-opacity hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40 dark:bg-ink-dark dark:text-paper-dark"
          >
            Export PDF
          </button>
        )}
        <ThemeToggle />
        <button
          type="button"
          onClick={onLogout}
          title={userEmail}
          className="rounded-md px-2 py-1 font-mono text-[11px] text-ink-muted transition-colors hover:bg-paper dark:text-ink-muted-dark dark:hover:bg-paper-dark"
        >
          Log out
        </button>
      </div>
    </header>
  )
}
