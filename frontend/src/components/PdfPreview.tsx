import { useEffect, useState } from 'react'

interface Props {
  available: boolean
  // Identifies which trip's PDF this is (a session_id or a share token) —
  // the effect keys off this primitive, not `fetchUrl` itself, so a fresh
  // closure identity on every parent render doesn't trigger a refetch, but
  // actually switching to a different trip (same `available` value) does.
  cacheKey: string
  // A thunk rather than a sessionId so this component works for both the
  // authenticated /export/{id}/pdf endpoint and the public
  // /shared/{token}/pdf one (SharedTripView) without knowing which.
  fetchUrl: () => Promise<string>
}

/** Renders the real generated PDF (Week 14) in an <iframe> — browsers render
 * PDFs natively, so a blob: URL from the /export endpoint (same
 * fetch-then-blob approach as the download button; a plain iframe src
 * can't attach the X-API-Key header) is all that's needed, no separate
 * PDF-to-image pipeline. */
export function PdfPreview({ available, cacheKey, fetchUrl }: Props) {
  const [url, setUrl] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    if (!available) return
    let objectUrl: string | null = null
    let cancelled = false
    fetchUrl()
      .then((u) => {
        if (cancelled) return
        objectUrl = u
        setUrl(u)
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err))
      })
    return () => {
      cancelled = true
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [available, cacheKey])

  if (!available) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center text-sm text-ink-muted dark:text-ink-muted-dark">
        PDF not generated for this trip yet.
      </div>
    )
  }
  if (error) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center text-sm text-red-600 dark:text-red-400">
        Couldn&apos;t load the PDF: {error}
      </div>
    )
  }
  if (!url) {
    return (
      <div className="flex h-full items-center justify-center p-8 text-center text-sm text-ink-muted dark:text-ink-muted-dark">
        Loading PDF…
      </div>
    )
  }
  return <iframe title="Itinerary PDF preview" src={url} className="h-full w-full" />
}
