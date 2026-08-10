import type { BudgetEvaluation, Itinerary } from '@/types/api'
import { formatCurrency } from '@/lib/currency'

interface Props {
  itinerary: Itinerary
  evaluation: BudgetEvaluation | null
}

const STATUS_STYLE: Record<string, string> = {
  under: 'text-emerald-700 dark:text-emerald-400',
  over: 'text-red-700 dark:text-red-400 font-semibold',
  on_target: 'text-ink-muted dark:text-ink-muted-dark',
}

export function BudgetPanel({ itinerary, evaluation }: Props) {
  // Line-item costs (flight/hotel/attraction/restaurant prices) are always
  // USD, as returned by their providers — only the aggregate `evaluation`
  // below is currency-converted (BudgetOptimizer.evaluate, backend), so
  // this fallback total (shown only when no evaluation exists yet) is
  // deliberately still formatted as USD rather than the stated
  // budget_currency.
  const totalCost =
    itinerary.days.flatMap((d) => d.items).reduce((sum, i) => sum + (i.cost ?? 0), 0) +
    (itinerary.hotel ? itinerary.hotel.price_per_night * Math.max(itinerary.days.length - 1, 1) : 0)

  if (!evaluation) {
    return (
      <div className="p-4">
        <p className="font-mono text-sm text-ink dark:text-ink-dark">
          Estimated total cost: <b>{formatCurrency(totalCost, 'USD')}</b>
        </p>
        <p className="mt-1 text-xs text-ink-muted dark:text-ink-muted-dark">
          No budget was stated for this trip, so there's nothing to evaluate against.
        </p>
      </div>
    )
  }

  const currency = itinerary.preferences.budget_currency

  return (
    <div className="p-4">
      <table className="w-full font-mono text-xs">
        <thead>
          <tr className="border-b border-line text-left text-ink-faint dark:border-line-dark dark:text-ink-faint-dark">
            <th className="pb-1.5 font-normal">Category</th>
            <th className="pb-1.5 text-right font-normal">Allocated</th>
            <th className="pb-1.5 text-right font-normal">Actual</th>
            <th className="pb-1.5 pl-3 text-right font-normal">Status</th>
          </tr>
        </thead>
        <tbody>
          {evaluation.categories.map((cat) => (
            <tr key={cat.category} className="border-b border-line last:border-b-0 dark:border-line-dark">
              <td className="py-1.5 text-ink capitalize dark:text-ink-dark">{cat.category}</td>
              <td className="py-1.5 text-right tabular-nums text-ink-muted dark:text-ink-muted-dark">
                {formatCurrency(cat.allocated, currency)}
              </td>
              <td className="py-1.5 text-right tabular-nums text-ink dark:text-ink-dark">
                {formatCurrency(cat.actual, currency)}
              </td>
              <td className={`py-1.5 pl-3 text-right capitalize ${STATUS_STYLE[cat.status] ?? ''}`}>
                {cat.status.replace('_', ' ')}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className="rounded-full border border-line px-2 py-0.5 font-mono text-[11px] tabular-nums text-ink-muted dark:border-line-dark dark:text-ink-muted-dark">
          TOTAL {formatCurrency(evaluation.total_actual, currency)} /{' '}
          {formatCurrency(evaluation.total_allocated, currency)}
        </span>
        {evaluation.adherence_score != null && (
          <span className="rounded-full border border-line px-2 py-0.5 font-mono text-[11px] tabular-nums text-ink-muted dark:border-line-dark dark:text-ink-muted-dark">
            ADHERENCE {(evaluation.adherence_score * 100).toFixed(0)}%
          </span>
        )}
      </div>

      {evaluation.suggestions.length > 0 && (
        <ul className="mt-3 space-y-1">
          {evaluation.suggestions.map((s, i) => (
            <li key={i} className="text-xs text-ink-muted dark:text-ink-muted-dark">
              &middot; {s}
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
