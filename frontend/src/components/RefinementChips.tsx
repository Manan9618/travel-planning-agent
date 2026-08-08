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
    <div className="flex flex-wrap gap-1.5 px-1">
      {COMMON_REFINEMENTS.map((label) => (
        <button
          key={label}
          type="button"
          disabled={disabled}
          onClick={() => onSelect(label)}
          className="rounded-full border border-line bg-paper px-2.5 py-1 font-mono text-[11px] text-ink-muted hover:border-accent hover:text-accent disabled:cursor-not-allowed disabled:opacity-40 dark:border-line-dark dark:bg-paper-dark dark:text-ink-muted-dark dark:hover:border-accent-dark dark:hover:text-accent-dark"
        >
          {label}
        </button>
      ))}
    </div>
  )
}
