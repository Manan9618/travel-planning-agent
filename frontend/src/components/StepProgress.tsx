import { PLANNING_STEPS, STEP_LABELS } from '@/types/api'

interface Props {
  completedSteps: string[]
  done: boolean
}

/** The agent's "thinking" state: a live checklist of the 11 planning steps
 * (Weeks 1-14's pipeline), each ticked off as its step_completed WS event
 * arrives, with the first not-yet-completed one pulsing as "in progress". */
export function StepProgress({ completedSteps, done }: Props) {
  const completedSet = new Set(completedSteps)
  const currentIndex = PLANNING_STEPS.findIndex((s) => !completedSet.has(s))

  return (
    <div
      className="rounded-lg border border-line bg-paper p-3 dark:border-line-dark dark:bg-paper-dark"
      role="status"
      aria-label="Planning progress"
    >
      <ul className="space-y-1.5">
        {PLANNING_STEPS.map((step, i) => {
          const isDone = completedSet.has(step)
          const isCurrent = !done && i === currentIndex
          return (
            <li key={step} className="flex items-center gap-2 font-mono text-xs">
              {isDone ? (
                <span className="flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full bg-accent text-[8px] text-white dark:bg-accent-dark">
                  ✓
                </span>
              ) : isCurrent ? (
                <span className="flex h-3.5 w-3.5 shrink-0 items-center justify-center">
                  <span className="h-2 w-2 animate-pulse rounded-full bg-accent dark:bg-accent-dark" />
                </span>
              ) : (
                <span className="h-3.5 w-3.5 shrink-0 rounded-full border-2 border-line dark:border-line-dark" />
              )}
              <span
                className={
                  isDone
                    ? 'text-ink-faint line-through dark:text-ink-faint-dark'
                    : isCurrent
                      ? 'font-medium text-ink dark:text-ink-dark'
                      : 'text-ink-faint dark:text-ink-faint-dark'
                }
              >
                {STEP_LABELS[step]}
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

/** Three-dot "typing" indicator shown while the agent is streaming its
 * narration (or generally "thinking") with no other content to show yet. */
export function TypingIndicator() {
  return (
    <div
      className="flex w-fit items-center gap-1 rounded-full border border-line bg-paper px-2.5 py-1.5 dark:border-line-dark dark:bg-paper-dark"
      role="status"
      aria-label="Agent is typing"
    >
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-ink-faint dark:bg-ink-faint-dark"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </div>
  )
}
