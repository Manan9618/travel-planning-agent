import type {
  AuthResponse,
  MessageResponse,
  PlanRequest,
  PlanResponse,
  RefineRequest,
  ResumeRequest,
  SessionListResponse,
  SessionStateResponse,
  ShareResponse,
  SharedTripResponse,
  UserResponse,
} from '@/types/api'

export const API_BASE_URL: string =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000'
const API_KEY: string | undefined = import.meta.env.VITE_API_KEY as string | undefined

// Real user accounts: the bearer token lives in localStorage (not just
// component state) so a page refresh doesn't silently log the user out —
// `api.ts` is a plain module, not a React component, so this is a simple
// get/set pair rather than context state; `AuthContext` (lib/useAuth.tsx)
// is the thing components actually interact with, and calls `setAuthToken`
// whenever it changes so every subsequent request picks it up immediately.
const AUTH_TOKEN_STORAGE_KEY = 'travel_agent_auth_token'

export function getAuthToken(): string | null {
  return localStorage.getItem(AUTH_TOKEN_STORAGE_KEY)
}

export function setAuthToken(token: string | null): void {
  if (token) localStorage.setItem(AUTH_TOKEN_STORAGE_KEY, token)
  else localStorage.removeItem(AUTH_TOKEN_STORAGE_KEY)
}

function authHeaders(): HeadersInit {
  const headers: Record<string, string> = {}
  if (API_KEY) headers['X-API-Key'] = API_KEY
  const token = getAuthToken()
  if (token) headers['Authorization'] = `Bearer ${token}`
  return headers
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

export function register(email: string, password: string): Promise<AuthResponse> {
  return request('/auth/register', { method: 'POST', body: JSON.stringify({ email, password }) })
}

export function login(email: string, password: string): Promise<AuthResponse> {
  return request('/auth/login', { method: 'POST', body: JSON.stringify({ email, password }) })
}

export function getCurrentUser(): Promise<UserResponse> {
  return request('/auth/me')
}

export function forgotPassword(email: string): Promise<MessageResponse> {
  return request('/auth/forgot-password', { method: 'POST', body: JSON.stringify({ email }) })
}

export function resetPassword(token: string, newPassword: string): Promise<MessageResponse> {
  return request('/auth/reset-password', {
    method: 'POST',
    body: JSON.stringify({ token, new_password: newPassword }),
  })
}

export function startPlan(rawText: string): Promise<PlanResponse> {
  const body: PlanRequest = { raw_text: rawText }
  return request('/plan', { method: 'POST', body: JSON.stringify(body) })
}

export function getPlan(sessionId: string): Promise<SessionStateResponse> {
  return request(`/plan/${sessionId}`)
}

export function listSessions(): Promise<SessionListResponse> {
  return request('/sessions')
}

export async function deleteSession(sessionId: string): Promise<void> {
  // Not routed through request<T>(): a 204 response has no body, and
  // request<T>() always calls res.json(), which throws on an empty body.
  const res = await fetch(`${API_BASE_URL}/sessions/${sessionId}`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${body}`)
  }
}

export function resumePlan(sessionId: string, approved: boolean): Promise<PlanResponse> {
  const body: ResumeRequest = { approved }
  return request(`/plan/${sessionId}/resume`, { method: 'POST', body: JSON.stringify(body) })
}

export function refinePlan(sessionId: string, rawText: string): Promise<PlanResponse> {
  const body: RefineRequest = { session_id: sessionId, raw_text: rawText }
  return request('/refine', { method: 'POST', body: JSON.stringify(body) })
}

export function createShareLink(sessionId: string): Promise<ShareResponse> {
  return request(`/plan/${sessionId}/share`, { method: 'POST' })
}

export async function revokeShareLink(sessionId: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/plan/${sessionId}/share`, {
    method: 'DELETE',
    headers: authHeaders(),
  })
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${body}`)
  }
}

// The /shared/{token} endpoints are deliberately public — no auth headers
// sent at all, since anyone with just the link (no account) is meant to
// be able to load them.

export async function getSharedTrip(token: string): Promise<SharedTripResponse> {
  const res = await fetch(`${API_BASE_URL}/shared/${token}`)
  if (!res.ok) {
    const body = await res.text()
    throw new Error(`${res.status} ${res.statusText}: ${body}`)
  }
  return res.json() as Promise<SharedTripResponse>
}

export async function fetchSharedPdfBlobUrl(token: string): Promise<string> {
  const res = await fetch(`${API_BASE_URL}/shared/${token}/pdf`)
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}`)
  const blob = await res.blob()
  return URL.createObjectURL(blob)
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

export function fetchCalendarBlobUrl(sessionId: string): Promise<string> {
  return fetchBlobUrl(`/export/${sessionId}/calendar`)
}

export async function downloadPdf(sessionId: string): Promise<void> {
  const url = await fetchPdfBlobUrl(sessionId)
  const a = document.createElement('a')
  a.href = url
  a.download = `itinerary-${sessionId}.pdf`
  a.click()
  URL.revokeObjectURL(url)
}

export async function downloadCalendar(sessionId: string): Promise<void> {
  const url = await fetchCalendarBlobUrl(sessionId)
  const a = document.createElement('a')
  a.href = url
  a.download = `itinerary-${sessionId}.ics`
  a.click()
  URL.revokeObjectURL(url)
}

export async function openInteractiveMap(sessionId: string): Promise<void> {
  const url = await fetchMapBlobUrl(sessionId)
  window.open(url, '_blank', 'noopener,noreferrer')
}

export function wsUrl(sessionId: string): string {
  const base = API_BASE_URL.replace(/^http/, 'ws')
  // A browser's native WebSocket API can't set an Authorization header, so
  // the bearer token travels as a query param instead — see WS /ws/{id}'s
  // own handling of this on the backend (app.py).
  const token = getAuthToken()
  const query = token ? `?token=${encodeURIComponent(token)}` : ''
  return `${base}/ws/${sessionId}${query}`
}
