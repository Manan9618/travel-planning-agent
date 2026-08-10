interface Props {
  onSignIn: () => void
  onGetStarted: () => void
}

// Real capabilities this project actually shipped (Weeks 8/13/14/20/21),
// not aspirational marketing copy — kept in sync with what the backend
// genuinely does rather than restated separately from it.
const FEATURES = [
  {
    badge: '5×',
    title: 'Parallel search',
    description:
      'Flights, hotels, attractions, restaurants, and weather are all searched at once — not one after another.',
  },
  {
    badge: '$',
    title: 'Budget-aware',
    description: 'Every itinerary is built and checked against your stated budget, tier by tier.',
  },
  {
    badge: '↻',
    title: 'Refine in plain English',
    description:
      'Ask for changes — "add a museum," "make it cheaper" — and only the affected parts re-plan.',
  },
  {
    badge: 'PDF',
    title: 'Take it with you',
    description:
      'An interactive map and a polished, printable itinerary PDF, generated from your real plan.',
  },
]

export function LandingPage({ onSignIn, onGetStarted }: Props) {
  return (
    <div className="flex h-full flex-col overflow-y-auto bg-paper font-sans dark:bg-paper-dark">
      <header className="flex items-center justify-between border-b border-line px-6 py-4 dark:border-line-dark">
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded bg-ink text-xs font-bold text-paper dark:bg-ink-dark dark:text-paper-dark">
            W
          </span>
          <span className="font-mono text-sm font-semibold tracking-wide text-ink dark:text-ink-dark">
            WAYPOINT
          </span>
        </div>
        <button
          type="button"
          onClick={onSignIn}
          className="rounded-lg border border-line px-3.5 py-1.5 font-mono text-xs font-medium text-ink transition-colors hover:bg-surface dark:border-line-dark dark:text-ink-dark dark:hover:bg-surface-dark"
        >
          Sign in
        </button>
      </header>

      <section className="mx-auto flex w-full max-w-3xl flex-1 flex-col items-center justify-center px-6 py-16 text-center">
        <span className="mb-4 rounded-full bg-accent-soft px-3 py-1 font-mono text-[11px] font-medium text-accent dark:bg-accent-soft-dark dark:text-accent-dark">
          AI-powered trip planning
        </span>
        <h1 className="text-4xl font-semibold leading-tight text-ink sm:text-5xl dark:text-ink-dark">
          Describe your trip.
          <br />
          Waypoint plans it.
        </h1>
        <p className="mt-4 max-w-xl text-base text-ink-muted dark:text-ink-muted-dark">
          Tell it a destination, a budget, and how you like to travel — Waypoint searches
          flights, hotels, attractions, restaurants, and weather, then builds a day-by-day
          itinerary you can refine in plain English.
        </p>
        <button
          type="button"
          onClick={onGetStarted}
          className="mt-8 rounded-lg bg-accent px-5 py-2.5 font-mono text-sm font-medium text-white transition-opacity hover:opacity-90 dark:bg-accent-dark dark:text-paper-dark"
        >
          Plan your first trip →
        </button>
        <p className="mt-3 font-mono text-[11px] text-ink-faint dark:text-ink-faint-dark">
          Free — takes about 30 seconds to sign up
        </p>
      </section>

      <section className="mx-auto grid w-full max-w-4xl grid-cols-1 gap-4 px-6 pb-16 sm:grid-cols-2 lg:grid-cols-4">
        {FEATURES.map((f) => (
          <div
            key={f.title}
            className="rounded-xl border border-line bg-surface p-4 dark:border-line-dark dark:bg-surface-dark"
          >
            <span className="mb-2 flex h-7 w-7 items-center justify-center rounded-full bg-accent font-mono text-[10px] font-bold text-white dark:bg-accent-dark dark:text-paper-dark">
              {f.badge}
            </span>
            <h3 className="text-sm font-semibold text-ink dark:text-ink-dark">{f.title}</h3>
            <p className="mt-1 text-xs text-ink-muted dark:text-ink-muted-dark">
              {f.description}
            </p>
          </div>
        ))}
      </section>

      <footer className="border-t border-line px-6 py-4 text-center font-mono text-[11px] text-ink-faint dark:border-line-dark dark:text-ink-faint-dark">
        Built with LangGraph, FastAPI, and React
      </footer>
    </div>
  )
}
