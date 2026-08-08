import type {
  PlanRequest,
  PlanResponse,
  RefineRequest,
  ResumeRequest,
  SessionStateResponse,
} from '@/types/api'

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000'
const API_KEY: string | undefined = import.meta.env.VITE_API_KEY as string | undefined

function authHeaders(): HeadersInit {
  return API_KEY ? { 'X-API-Key': API_KEY } : {}
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...authHeaders(), ...init?.headers },
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${body}`)
  }
  return res.json() as Promise<T>
}

export function startPlan(rawText: string): Promise<PlanResponse> {
  const body: PlanRequest = { raw_text: rawText }
  return request('/plan', { method: 'POST', body: JSON.stringify(body) })
}

export function getPlan(sessionId: string): Promise<SessionStateResponse> {
  return request(`/plan/${sessionId}`)
}

export function resumePlan(sessionId: string, approved: boolean): Promise<PlanResponse> {
  const body: ResumeRequest = { approved }
  return request(`/plan/${sessionId}/resume`, { method: 'POST', body: JSON.stringify(body) })
}

export function refinePlan(sessionId: string, rawText: string): Promise<PlanResponse> {
  const body: RefineRequest = { session_id: sessionId, raw_text: rawText }
  return request('/refine', { method: 'POST', body: JSON.stringify(body) })
}

// The /export endpoints are behind the same X-API-Key check as everything
// else, which a plain <a href> or <iframe src> can't attach — so both of
// these fetch with the header, then hand the browser a blob: URL instead of
// linking straight to the API URL.

async function fetchBlobUrl(path: string): Promise<string> {
  const res = await fetch(`${API_BASE_URL}${path}`, { headers: authHeaders() })
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  const blob = await res.blob()
  return URL.createObjectURL(blob)
}

export function fetchPdfBlobUrl(sessionId: string): Promise<string> {
  return fetchBlobUrl(`/export/${sessionId}/pdf`)
}

export function fetchMapBlobUrl(sessionId: string): Promise<string> {
  return fetchBlobUrl(`/export/${sessionId}/map`)
}

export async function downloadPdf(sessionId: string): Promise<void> {
  const url = await fetchPdfBlobUrl(sessionId)
  const a = document.createElement('a')
  a.href = url
  a.download = `itinerary-${sessionId}.pdf`
  a.click()
  URL.revokeObjectURL(url)
}

export async function openInteractiveMap(sessionId: string): Promise<void> {
  const url = await fetchMapBlobUrl(sessionId)
  window.open(url, '_blank', 'noopener,noreferrer')
}

export function wsUrl(sessionId: string): string {
  const base = API_BASE_URL.replace(/^http/, 'ws')
  return `${base}/ws/${sessionId}`
}
