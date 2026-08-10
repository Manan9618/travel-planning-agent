import { useEffect, useRef, useState } from 'react'
import { downloadPdf, getPlan, refinePlan, resumePlan, startPlan } from '@/lib/api'
import { usePlanningProgress } from '@/lib/useWebSocket'
import { useAuth } from '@/lib/useAuth'
import type { SessionStateResponse, SessionSummary } from '@/types/api'
import { AuthPage } from '@/components/AuthPage'
import { LandingPage } from '@/components/LandingPage'
import { Dashboard } from '@/components/Dashboard'
import { Header } from '@/components/Header'
import { MessageBubble } from '@/components/MessageBubble'
import { ChatInput } from '@/components/ChatInput'
import { StepProgress, TypingIndicator } from '@/components/StepProgress'
import { RunSummary } from '@/components/RunSummary'
import { RefinementChips } from '@/components/RefinementChips'
import { HumanReviewPrompt } from '@/components/HumanReviewPrompt'
import { Tabs } from '@/components/Tabs'
import { ItineraryPanel } from '@/components/ItineraryPanel'
import { BudgetPanel } from '@/components/BudgetPanel'
import { MapPreview } from '@/components/MapPreview'
import { PdfPreview } from '@/components/PdfPreview'

interface Turn {
  sessionId: string
  userText: string
  final: SessionStateResponse | null
  narration: string
}

function App() {
  const { user, loading: authLoading, logout } = useAuth()
  const [showAuth, setShowAuth] = useState(false)
  const [showDashboard, setShowDashboard] = useState(true)
  const [turns, setTurns] = useState<Turn[]>([])
  const [liveSessionId, setLiveSessionId] = useState<string | null>(null)
  const [epoch, setEpoch] = useState(0)
  const [deciding, setDeciding] = useState(false)
  const [sendError, setSendError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState('itinerary')
  const [mobileView, setMobileView] = useState<'chat' | 'canvas'>('chat')
  const inputRef = useRef<HTMLTextAreaElement | null>(null)
  const bottomRef = useRef<HTMLDivElement | null>(null)

  const progress = usePlanningProgress(liveSessionId, epoch)
  const lastTurn = turns[turns.length - 1] ?? null

  // The canvas shows the most recent turn that actually produced an
  // itinerary — while a refinement is still streaming (or paused awaiting
  // review), the previous itinerary stays visible instead of the canvas
  // going blank.
  const displayState = [...turns].reverse().find((t) => t.final?.itinerary)?.final ?? null

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
      const res = isRefining ? await refinePlan(lastTurn!.sessionId, text) : await startPlan(text)
      setTurns((prev) => [
        ...prev,
        { sessionId: res.session_id, userText: text, final: null, narration: '' },
      ])
      setLiveSessionId(res.session_id)
      setEpoch((e) => e + 1)
      setMobileView('chat')
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

  function startNewTrip() {
    setTurns([])
    setSendError(null)
    setMobileView('chat')
    setShowDashboard(false)
    inputRef.current?.focus()
  }

  async function openSession(session: SessionSummary) {
    setShowDashboard(false)
    setSendError(null)
    try {
      const state = await getPlan(session.session_id)
      setTurns([{ sessionId: session.session_id, userText: session.raw_text, final: state, narration: '' }])
      if (state.status === 'running') {
        setLiveSessionId(session.session_id)
        setEpoch((e) => e + 1)
      }
    } catch (err) {
      setSendError(err instanceof Error ? err.message : String(err))
    }
  }

  if (authLoading) {
    return (
      <div className="flex h-full items-center justify-center bg-paper font-mono text-xs text-ink-faint dark:bg-paper-dark dark:text-ink-faint-dark">
        Loading…
      </div>
    )
  }

  if (!user) {
    return showAuth ? (
      <AuthPage onBack={() => setShowAuth(false)} />
    ) : (
      <LandingPage onSignIn={() => setShowAuth(true)} onGetStarted={() => setShowAuth(true)} />
    )
  }

  return (
    <div className="flex h-full flex-col bg-paper font-sans dark:bg-paper-dark">
      <Header
        itinerary={displayState?.itinerary ?? null}
        onNewTrip={startNewTrip}
        onDownloadPdf={() => displayState && handleDownloadPdf(displayState.session_id)}
        onMyTrips={() => setShowDashboard(true)}
        pdfAvailable={Boolean(displayState?.pdf_path)}
        hasTurns={turns.length > 0}
        userEmail={user.email}
        onLogout={logout}
      />

      {showDashboard ? (
        <Dashboard onNewTrip={startNewTrip} onSelect={openSession} />
      ) : (
        <div className="flex min-h-0 flex-1">
          {/* Chat rail */}
          <div
            className={[
              'flex-col sm:flex sm:w-[380px] sm:shrink-0 sm:border-r sm:border-line md:w-[420px] dark:sm:border-line-dark',
              mobileView === 'canvas' ? 'hidden' : 'flex',
              'w-full',
            ].join(' ')}
          >
            <main className="flex-1 space-y-3 overflow-y-auto p-3">
              {turns.length === 0 && (
                <div className="flex h-full flex-col items-center justify-center gap-2 px-4 text-center">
                  <p className="text-sm text-ink-muted dark:text-ink-muted-dark">
                    Try:{' '}
                    <i>
                      &ldquo;5 days in Paris this September under $2000, I love art and
                      museums&rdquo;
                    </i>
                  </p>
                </div>
              )}

              {turns.map((turn) => {
                const isLive = liveSessionId === turn.sessionId
                return (
                  <div key={turn.sessionId} className="space-y-2">
                    <MessageBubble role="user">{turn.userText}</MessageBubble>

                    {isLive && (
                      <div className="flex flex-col items-start gap-2">
                        <StepProgress
                          completedSteps={progress.completedSteps}
                          done={progress.done}
                        />
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

                    {!isLive && turn.narration && (
                      <MessageBubble role="assistant">{turn.narration}</MessageBubble>
                    )}

                    {!isLive && turn.final?.itinerary && (
                      <div className="space-y-2">
                        <RunSummary state={turn.final} />
                        <button
                          type="button"
                          onClick={() => setMobileView('canvas')}
                          className="rounded-md border border-line px-2 py-1 font-mono text-[11px] text-ink-muted transition-colors hover:text-ink sm:hidden dark:border-line-dark dark:text-ink-muted-dark dark:hover:text-ink-dark"
                        >
                          View itinerary →
                        </button>
                      </div>
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
              <div className="px-3 pb-2">
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

          {/* Canvas */}
          <div
            className={['min-w-0 flex-1 sm:flex', mobileView === 'chat' ? 'hidden' : 'flex'].join(
              ' ',
            )}
          >
            {displayState?.itinerary ? (
              <Tabs
                tabs={[
                  { id: 'itinerary', label: 'Itinerary' },
                  { id: 'map', label: 'Map' },
                  { id: 'budget', label: 'Budget' },
                  { id: 'pdf', label: 'PDF preview', disabled: !displayState.pdf_path },
                ]}
                active={activeTab}
                onChange={setActiveTab}
              >
                {activeTab === 'itinerary' && <ItineraryPanel itinerary={displayState.itinerary} />}
                {activeTab === 'map' && (
                  <MapPreview itinerary={displayState.itinerary} className="h-full w-full" />
                )}
                {activeTab === 'budget' && (
                  <BudgetPanel
                    itinerary={displayState.itinerary}
                    evaluation={displayState.budget_evaluation}
                  />
                )}
                {activeTab === 'pdf' && (
                  <PdfPreview
                    sessionId={displayState.session_id}
                    available={Boolean(displayState.pdf_path)}
                  />
                )}
              </Tabs>
            ) : (
              <div className="flex h-full w-full items-center justify-center p-8 text-center font-mono text-xs text-ink-faint dark:text-ink-faint-dark">
                Your itinerary will appear here once it&apos;s built.
              </div>
            )}
          </div>
        </div>
      )}

      {!showDashboard && displayState?.itinerary && (
        <div className="flex shrink-0 border-t border-line sm:hidden dark:border-line-dark">
          <button
            type="button"
            onClick={() => setMobileView('chat')}
            className={`flex-1 py-2 font-mono text-xs ${mobileView === 'chat' ? 'text-ink dark:text-ink-dark' : 'text-ink-faint dark:text-ink-faint-dark'}`}
          >
            Chat
          </button>
          <button
            type="button"
            onClick={() => setMobileView('canvas')}
            className={`flex-1 py-2 font-mono text-xs ${mobileView === 'canvas' ? 'text-ink dark:text-ink-dark' : 'text-ink-faint dark:text-ink-faint-dark'}`}
          >
            Itinerary
          </button>
        </div>
      )}
    </div>
  )
}

export default App
