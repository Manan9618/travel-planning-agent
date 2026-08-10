import { useEffect, useState } from 'react'
import { fetchSharedPdfBlobUrl, getSharedTrip } from '@/lib/api'
import type { SharedTripResponse } from '@/types/api'
import { destinationLabel } from '@/lib/destinations'
import { ItineraryPanel } from '@/components/ItineraryPanel'
import { MapPreview } from '@/components/MapPreview'
import { BudgetPanel } from '@/components/BudgetPanel'
import { PdfPreview } from '@/components/PdfPreview'
import { Tabs } from '@/components/Tabs'

interface Props {
  token: string
  onPlanYourOwn: () => void
}

/** Public, read-only view of a shared trip — reachable via GET /shared/{token}
 * with no account at all. Reuses the same ItineraryPanel/MapPreview/
 * BudgetPanel the owner's own canvas uses (all three take an `itinerary`
 * object directly, no auth-gated fetch inside them), and a `PdfPreview`
 * pointed at the public /shared/{token}/pdf endpoint instead of the
 * authenticated /export one. */
export function SharedTripView({ token, onPlanYourOwn }: Props) {
  const [trip, setTrip] = useState<SharedTripResponse | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState('itinerary')

  useEffect(() => {
    let cancelled = false
    getSharedTrip(token)
      .then((t) => {
        if (!cancelled) setTrip(t)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      })
    return () => {
      cancelled = true
    }
  }, [token])

  if (error) {
    return (
      <div className="flex h-full flex-col items-center justify-center gap-3 bg-paper px-4 text-center font-sans dark:bg-paper-dark">
        <p className="text-sm text-ink-muted dark:text-ink-muted-dark">
          This shared link is invalid or no longer available.
        </p>
        <button
          type="button"
          onClick={onPlanYourOwn}
          className="rounded-lg bg-accent px-3.5 py-2 font-mono text-xs font-medium text-white transition-opacity hover:opacity-90 dark:bg-accent-dark dark:text-paper-dark"
        >
          Plan your own trip
        </button>
      </div>
    )
  }

  if (!trip || !trip.itinerary) {
    return (
      <div className="flex h-full items-center justify-center bg-paper font-mono text-xs text-ink-faint dark:bg-paper-dark dark:text-ink-faint-dark">
        Loading shared trip…
      </div>
    )
  }

  const itinerary = trip.itinerary

  return (
    <div className="flex h-full flex-col bg-paper font-sans dark:bg-paper-dark">
      <header className="flex items-center justify-between gap-4 border-b border-line bg-surface px-4 py-2.5 dark:border-line-dark dark:bg-surface-dark">
        <div className="flex min-w-0 items-center gap-2">
          <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded bg-ink text-[10px] font-bold text-paper dark:bg-ink-dark dark:text-paper-dark">
            W
          </span>
          <span className="truncate text-sm font-semibold text-ink dark:text-ink-dark">
            {destinationLabel(itinerary.preferences)} — shared trip
          </span>
        </div>
        <button
          type="button"
          onClick={onPlanYourOwn}
          className="shrink-0 rounded-lg bg-accent px-3 py-1.5 font-mono text-[11px] font-medium text-white transition-opacity hover:opacity-90 dark:bg-accent-dark dark:text-paper-dark"
        >
          Plan your own trip
        </button>
      </header>

      <div className="min-h-0 flex-1">
        <Tabs
          tabs={[
            { id: 'itinerary', label: 'Itinerary' },
            { id: 'map', label: 'Map' },
            { id: 'budget', label: 'Budget' },
            { id: 'pdf', label: 'PDF preview', disabled: !trip.pdf_available },
          ]}
          active={activeTab}
          onChange={setActiveTab}
        >
          {activeTab === 'itinerary' && <ItineraryPanel itinerary={itinerary} />}
          {activeTab === 'map' && <MapPreview itinerary={itinerary} className="h-full w-full" />}
          {activeTab === 'budget' && (
            <BudgetPanel itinerary={itinerary} evaluation={trip.budget_evaluation} />
          )}
          {activeTab === 'pdf' && (
            <PdfPreview
              cacheKey={token}
              fetchUrl={() => fetchSharedPdfBlobUrl(token)}
              available={trip.pdf_available}
            />
          )}
        </Tabs>
      </div>
    </div>
  )
}
