const COMMON_REFINEMENTS = [
  'Less walking',
  'Upgrade the hotel',
  'Add a museum',
  'More budget-friendly',
  'Add a free day',
  'More outdoor activities',
]

interface Props {
  onSelect: (text: string) => void
  disabled: boolean
}

/** One-tap common refinement requests (Week 16 plan deliverable), each just
 * sends its label straight to /refine — PreferenceParser (Week 1) already
 * handles free-text refinement requests like these. */
export function RefinementChips({ onSelect, disabled }: Props) {
  return (
    <div className="flex flex-wrap gap-2 px-1">
      {COMMON_REFINEMENTS.map((label) => (
        <button
          key={label}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(label)}
          className="rounded-full border border-indigo-200 bg-indigo-50 px-3 py-1 text-xs font-medium text-indigo-700 hover:bg-indigo-100 disabled:cursor-not-allowed disabled:opacity-40 dark:border-indigo-800 dark:bg-indigo-950 dark:text-indigo-300 dark:hover:bg-indigo-900"
        >
          {label}
        </button>
      ))}
    </div>
  )
}
