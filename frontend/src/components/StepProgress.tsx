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
      className="w-full max-w-sm rounded-xl border border-gray-200 bg-white p-3 shadow-sm dark:border-gray-700 dark:bg-gray-900"
      role="status"
      aria-label="Planning progress"
    >
      <ul className="space-y-1.5">
        {PLANNING_STEPS.map((step, i) => {
          const isDone = completedSet.has(step)
          const isCurrent = !done && i === currentIndex
          return (
            <li key={step} className="flex items-center gap-2 text-sm">
              {isDone ? (
                <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-green-500 text-[10px] text-white">
                  ✓
                </span>
              ) : isCurrent ? (
                <span className="flex h-4 w-4 shrink-0 items-center justify-center">
                  <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-indigo-500" />
                </span>
              ) : (
                <span className="h-4 w-4 shrink-0 rounded-full border-2 border-gray-200 dark:border-gray-700" />
              )}
              <span
                className={
                  isDone
                    ? 'text-gray-400 line-through dark:text-gray-600'
                    : isCurrent
                      ? 'font-medium text-gray-900 dark:text-gray-100'
                      : 'text-gray-400 dark:text-gray-600'
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
      className="flex w-fit items-center gap-1 rounded-full bg-gray-100 px-3 py-2 dark:bg-gray-800"
      role="status"
      aria-label="Agent is typing"
    >
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          className="h-1.5 w-1.5 animate-bounce rounded-full bg-gray-400 dark:bg-gray-500"
          style={{ animationDelay: `${i * 0.15}s` }}
        />
      ))}
    </div>
  )
}
