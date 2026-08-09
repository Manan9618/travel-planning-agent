import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { usePlanningProgress } from '@/lib/useWebSocket'

/** Minimal fake WebSocket: real enough for usePlanningProgress's own usage
 * (assigns onopen/onclose/onmessage, calls .close()) without spinning up a
 * real socket or server, matching how this hook is actually driven — no
 * existing test in this repo mocks WebSocket yet, so this is deliberately
 * small rather than a general-purpose fake. */
class FakeWebSocket {
  static instances: FakeWebSocket[] = []
  onopen: (() => void) | null = null
  onclose: (() => void) | null = null
  onmessage: ((event: { data: string }) => void) | null = null
  closed = false

  constructor(public url: string) {
    FakeWebSocket.instances.push(this)
  }

  close() {
    this.closed = true
    this.onclose?.()
  }

  emit(data: unknown) {
    this.onmessage?.({ data: JSON.stringify(data) })
  }
}

describe('usePlanningProgress', () => {
  beforeEach(() => {
    FakeWebSocket.instances = []
    vi.stubGlobal('WebSocket', FakeWebSocket)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('marks reused steps from a refinement_seeded event as completed', async () => {
    const { result } = renderHook(() => usePlanningProgress('session-1'))
    const socket = FakeWebSocket.instances[0]

    act(() => {
      socket.emit({
        type: 'refinement_seeded',
        reused_steps: ['search_flights', 'search_hotels'],
      })
    })

    await waitFor(() => {
      expect(result.current.completedSteps).toEqual(['search_flights', 'search_hotels'])
    })
  })

  it('appends step_completed events after reused steps without overwriting them', async () => {
    const { result } = renderHook(() => usePlanningProgress('session-1'))
    const socket = FakeWebSocket.instances[0]

    act(() => {
      socket.emit({ type: 'refinement_seeded', reused_steps: ['search_flights'] })
    })
    act(() => {
      socket.emit({ type: 'step_completed', step: 'find_attractions', errors: [] })
    })

    await waitFor(() => {
      expect(result.current.completedSteps).toEqual(['search_flights', 'find_attractions'])
    })
  })

  it('starts with no completed steps for a plain /plan session (no refinement_seeded event)', () => {
    const { result } = renderHook(() => usePlanningProgress('session-1'))
    expect(result.current.completedSteps).toEqual([])
  })
})
