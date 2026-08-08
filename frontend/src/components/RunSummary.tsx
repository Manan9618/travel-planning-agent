import type { SessionStateResponse } from '@/types/api'

interface Props {
  state: SessionStateResponse
}

function Badge({ children, tone = 'default' }: { children: React.ReactNode; tone?: 'default' | 'warn' }) {
  return (
    <span
      className={[
        'rounded-full border px-2 py-0.5 font-mono text-[10px] tabular-nums',
        tone === 'warn'
          ? 'border-amber-300 bg-amber-50 text-amber-800 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-300'
          : 'border-line bg-paper text-ink-muted dark:border-line-dark dark:bg-paper-dark dark:text-ink-muted-dark',
      ].join(' ')}
    >
      {children}
    </span>
  )
}

/** Real, computed stats about the finished run — every number here comes
 * straight from the session state (no invented "N tool calls" or timing
 * data the backend doesn't currently track). */
export function RunSummary({ state }: Props) {
  const itinerary = state.itinerary
  if (!itinerary) return null

  const badges: React.ReactNode[] = []

  badges.push(
    <Badge key="days">
      {itinerary.days.length} DAY{itinerary.days.length !== 1 ? 'S' : ''}
    </Badge>,
  )

  if (state.budget_evaluation?.adherence_score != null) {
    badges.push(
      <Badge key="budget">BUDGET {(state.budget_evaluation.adherence_score * 100).toFixed(0)}%</Badge>,
    )
  }

  if (state.conflict_log.length > 0) {
    const resolved = state.conflict_log.filter((c) => c.resolved).length
    badges.push(
      <Badge key="conflicts">
        {resolved}/{state.conflict_log.length} CONFLICTS RESOLVED
      </Badge>,
    )
  }

  const mustSee = itinerary.preferences.must_see
  if (mustSee.length > 0) {
    const titles = itinerary.days.flatMap((d) => d.items.map((i) => i.title.toLowerCase()))
    const hits = mustSee.filter((term) => titles.some((t) => t.includes(term.toLowerCase()))).length
    badges.push(
      <Badge key="mustsee">
        {hits}/{mustSee.length} MUST-SEE
      </Badge>,
    )
  }

  if (state.unresolved_conflicts.length > 0) {
    badges.push(
      <Badge key="unresolved" tone="warn">
        {state.unresolved_conflicts.length} UNRESOLVED
      </Badge>,
    )
  }

  return <div className="flex flex-wrap gap-1.5">{badges}</div>
}
