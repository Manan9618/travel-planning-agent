import { useEffect, useRef, useState } from 'react'
import { downloadPdf, openInteractiveMap, refinePlan, resumePlan, startPlan, getPlan } from '@/lib/api'
import { usePlanningProgress } from '@/lib/useWebSocket'
import type { SessionStateResponse } from '@/types/api'
import { MessageBubble } from '@/components/MessageBubble'
import { ChatInput } from '@/components/ChatInput'
import { StepProgress, TypingIndicator } from '@/components/StepProgress'
import { ItineraryCard } from '@/components/ItineraryCard'
import { RefinementChips } from '@/components/RefinementChips'
import { HumanReviewPrompt } from '@/components/HumanReviewPrompt'
import { ThemeToggle } from '@/components/ThemeToggle'

interface Turn {
  sessionId: string
  userText: string
  final: SessionStateResponse | null
  narration: string
}

function App() {
  const [turns, setTurns] = useState<Turn[]>([])
  const [liveSessionId, setLiveSessionId] = useState<string | null>(null)
  const [epoch, setEpoch] = useState(0)
  const [deciding, setDeciding] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)
  const inputRef = useRef<HTMLTextAreaElement | null>(null)
  const bottomRef = useRef<HTMLDivElement | null>(null)

  const progress = usePlanningProgress(liveSessionId, epoch)
  const lastTurn = turns[turns.length - 1] ?? null

  // Once the live run reaches a terminal WS state (done / awaiting_review /
  // error — Week 15's TERMINAL_EVENT_TYPES, which close the socket), fetch
  // the full session state once via REST (the WS only streams progress
  // events, not the itinerary/budget/PDF payload itself) and fold it into
  // that turn.
  useEffect(() => {
    if (!liveSessionId) return
    if (!(progress.done || progress.awaitingReview || progress.errorMessage)) return
    let cancelled = false
    getPlan(liveSessionId)
      .then((state) => {
        if (cancelled) return
        setTurns((prev) =>
          prev.map((t) =>
            t.sessionId === liveSessionId ? { ...t, final: state, narration: progress.narration } : t,
          ),
        )
        setLiveSessionId(null)
      })
      .catch((err) => {
        if (!cancelled) setSendError(err instanceof Error ? err.message : String(err))
      })
    return () => {
      cancelled = true
    }
  }, [liveSessionId, progress.done, progress.awaitingReview, progress.errorMessage, progress.narration])

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [turns, progress.narration, progress.completedSteps])

  // Keyboard shortcuts: Ctrl/Cmd+K focuses the input from anywhere.
  useEffect(() => {
    const handler = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        inputRef.current?.focus()
      }
    }
    window.addEventListener('keydown', handler)
    return () => window.removeEventListener('keydown', handler)
  }, [])

  const isRefining = Boolean(lastTurn?.final?.itinerary)
  const isBusy = liveSessionId !== null || deciding
  const isAwaitingReview = lastTurn?.final?.status === 'awaiting_review' && !isBusy

  async function handleSend(text: string) {
    setSendError(null)
    try {
      const res = isRefining
        ? await refinePlan(lastTurn!.sessionId, text)
        : await startPlan(text)
      setTurns((prev) => [...prev, { sessionId: res.session_id, userText: text, final: null, narration: '' }])
      setLiveSessionId(res.session_id)
      setEpoch((e) => e + 1)
    } catch (err) {
      setSendError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleDecision(approved: boolean) {
    if (!lastTurn) return
    setDeciding(true)
    try {
      await resumePlan(lastTurn.sessionId, approved)
      setLiveSessionId(lastTurn.sessionId)
      setEpoch((e) => e + 1)
    } catch (err) {
      setSendError(err instanceof Error ? err.message : String(err))
    } finally {
      setDeciding(false)
    }
  }

  async function handleDownloadPdf(sessionId: string) {
    try {
      await downloadPdf(sessionId)
    } catch (err) {
      setSendError(err instanceof Error ? err.message : String(err))
    }
  }

  async function handleOpenMap(sessionId: string) {
    try {
      await openInteractiveMap(sessionId)
    } catch (err) {
      setSendError(err instanceof Error ? err.message : String(err))
    }
  }

  function startNewTrip() {
    setTurns([])
    setSendError(null)
    inputRef.current?.focus()
  }

  return (
    <div className="mx-auto flex h-full max-w-3xl flex-col bg-white dark:bg-gray-950">
      <header className="flex items-center justify-between border-b border-gray-200 px-4 py-3 dark:border-gray-800">
        <div>
          <h1 className="text-sm font-semibold text-gray-900 dark:text-gray-100">
            AI Travel Planning Agent
          </h1>
          <p className="text-xs text-gray-400">Describe a trip and I'll plan it end to end</p>
        </div>
        <div className="flex items-center gap-1">
          {turns.length > 0 && (
            <button
              type="button"
              onClick={startNewTrip}
              className="rounded-md px-2 py-1 text-xs font-medium text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
            >
              New trip
            </button>
          )}
          <ThemeToggle />
        </div>
      </header>

      <main className="flex-1 space-y-4 overflow-y-auto px-4 py-4">
        {turns.length === 0 && (
          <div className="flex h-full flex-col items-center justify-center gap-3 text-center text-gray-400">
            <p className="text-sm">
              Try: <i>"5 days in Paris this September under $2000, I love art and museums"</i>
            </p>
          </div>
        )}

        {turns.map((turn) => {
          const isLive = liveSessionId === turn.sessionId
          return (
            <div key={turn.sessionId} className="space-y-3">
              <MessageBubble role="user">{turn.userText}</MessageBubble>

              {isLive && (
                <div className="flex flex-col items-start gap-2">
                  <StepProgress completedSteps={progress.completedSteps} done={progress.done} />
                  {progress.narration ? (
                    <MessageBubble role="assistant">{progress.narration}</MessageBubble>
                  ) : (
                    <TypingIndicator />
                  )}
                </div>
              )}

              {!isLive && turn.final?.status === 'awaiting_review' && (
                <HumanReviewPrompt
                  conflicts={turn.final.unresolved_conflicts}
                  onDecide={handleDecision}
                  deciding={deciding}
                />
              )}

              {!isLive && turn.narration && <MessageBubble role="assistant">{turn.narration}</MessageBubble>}

              {!isLive && turn.final?.itinerary && (
                <ItineraryCard
                  itinerary={turn.final.itinerary}
                  budgetEvaluation={turn.final.budget_evaluation}
                  pdfAvailable={Boolean(turn.final.pdf_path)}
                  mapAvailable={turn.final.map_html_available}
                  onDownloadPdf={() => handleDownloadPdf(turn.sessionId)}
                  onOpenMap={() => handleOpenMap(turn.sessionId)}
                />
              )}

              {!isLive && turn.final && turn.final.status === 'failed' && (
                <MessageBubble role="assistant" tone="error">
                  Something went wrong: {turn.final.errors.join('; ') || 'unknown error'}
                </MessageBubble>
              )}
            </div>
          )
        })}

        {sendError && (
          <MessageBubble role="assistant" tone="error">
            {sendError}
          </MessageBubble>
        )}

        <div ref={bottomRef} />
      </main>

      {isRefining && !isBusy && !isAwaitingReview && (
        <div className="px-4 pb-2">
          <RefinementChips onSelect={handleSend} disabled={isBusy} />
        </div>
      )}

      <ChatInput
        ref={inputRef}
        onSend={handleSend}
        disabled={isBusy || isAwaitingReview}
        placeholder={
          isAwaitingReview
            ? 'Approve or reject above to continue…'
            : isRefining
              ? 'Refine your trip…'
              : 'Describe your trip…'
        }
      />
    </div>
  )
}

export default App
