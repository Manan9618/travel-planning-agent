import { useEffect, useRef, useState } from 'react'
import { wsUrl } from '@/lib/api'
import type { WsEvent } from '@/types/api'

export interface PlanningProgress {
  connectionState: 'connecting' | 'open' | 'closed'
  completedSteps: string[]
  narration: string
  awaitingReview: boolean
  done: boolean
  errorMessage: string | null
}

const INITIAL_PROGRESS: PlanningProgress = {
  connectionState: 'connecting',
  completedSteps: [],
  narration: '',
  awaitingReview: false,
  done: false,
  errorMessage: null,
}

/** Connects to /ws/{sessionId} and folds the event stream (Week 15's
 * step_completed / narration_token / awaiting_review / done / error events)
 * into one progress object the UI renders from. Reconnects to a fresh
 * session cleanly whenever sessionId changes.
 *
 * `epoch` forces a fresh reconnect even when sessionId stays the same —
 * needed after a human-review resume(), which re-invokes the same
 * thread_id/session and streams a fresh round of narration + a new "done"
 * event, but the backend already closed the original socket on the
 * awaiting_review event (one of Week 15's TERMINAL_EVENT_TYPES).
 */
export function usePlanningProgress(
  sessionId: string | null,
  epoch: number = 0,
): PlanningProgress {
  const [progress, setProgress] = useState<PlanningProgress>(INITIAL_PROGRESS)
  const socketRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    if (!sessionId) {
      setProgress(INITIAL_PROGRESS)
      return
    }
    setProgress(INITIAL_PROGRESS)

    const socket = new WebSocket(wsUrl(sessionId))
    socketRef.current = socket

    socket.onopen = () => setProgress((p) => ({ ...p, connectionState: 'open' }))
    socket.onclose = () => setProgress((p) => ({ ...p, connectionState: 'closed' }))

    socket.onmessage = (event) => {
      const data = JSON.parse(event.data as string) as WsEvent
      setProgress((p) => {
        switch (data.type) {
          case 'step_completed':
            return { ...p, completedSteps: [...p.completedSteps, data.step] }
          case 'refinement_seeded':
            // Reused steps (Week 21) never get their own step_completed
            // event — the graph skips calling them entirely — so this is
            // the only signal the UI gets that they're already done.
            return { ...p, completedSteps: [...p.completedSteps, ...data.reused_steps] }
          case 'narration_token':
            return { ...p, narration: p.narration + data.token }
          case 'awaiting_review':
            return { ...p, awaitingReview: true }
          case 'done':
            return { ...p, done: true }
          case 'error':
            return { ...p, errorMessage: data.message }
          default:
            return p
        }
      })
    }

    return () => {
      socket.close()
      socketRef.current = null
    }
  }, [sessionId, epoch])

  return progress
}
