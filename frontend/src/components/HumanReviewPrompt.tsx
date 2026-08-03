import type { Conflict } from '@/types/api'

interface Props {
  conflicts: Conflict[]
  onDecide: (approved: boolean) => void
  deciding: boolean
}

/** Week 6's human-in-the-loop step, surfaced in the UI: some conflicts
 * (usually a budget overrun ConflictResolver couldn't fix by trimming
 * optional items) need an explicit yes/no before the plan is finalized. */
export function HumanReviewPrompt({ conflicts, onDecide, deciding }: Props) {
  return (
    <div className="w-full max-w-xl rounded-xl border border-amber-300 bg-amber-50 p-4 dark:border-amber-800 dark:bg-amber-950">
      <h3 className="text-sm font-semibold text-amber-900 dark:text-amber-200">
        A few things couldn't be auto-resolved
      </h3>
      <ul className="mt-2 space-y-1">
        {conflicts.map((c, i) => (
          <li key={i} className="text-sm text-amber-800 dark:text-amber-300">
            {c.description}
          </li>
        ))}
      </ul>
      <div className="mt-3 flex gap-2">
        <button
          type="button"
          disabled={deciding}
          onClick={() => onDecide(true)}
          className="rounded-md bg-amber-600 px-3 py-1.5 text-xs font-medium text-white hover:bg-amber-700 disabled:opacity-50"
        >
          Approve anyway
        </button>
        <button
          type="button"
          disabled={deciding}
          onClick={() => onDecide(false)}
          className="rounded-md border border-amber-300 px-3 py-1.5 text-xs font-medium text-amber-800 hover:bg-amber-100 disabled:opacity-50 dark:border-amber-700 dark:text-amber-200 dark:hover:bg-amber-900"
        >
          Reject
        </button>
      </div>
    </div>
  )
}
