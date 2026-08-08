import { describe, expect, it } from 'vitest'
import { estimatedWalkMinutes, haversineKm } from './geo'

describe('haversineKm', () => {
  it('returns 0 for identical points', () => {
    expect(haversineKm([48.85, 2.35], [48.85, 2.35])).toBe(0)
  })

  it('returns a plausible distance for two known Paris landmarks', () => {
    // Eiffel Tower to Louvre, real-world distance ~4km
    const km = haversineKm([48.8584, 2.2945], [48.8606, 2.3376])
    expect(km).toBeGreaterThan(3)
    expect(km).toBeLessThan(5)
  })
})

describe('estimatedWalkMinutes', () => {
  it('estimates ~12 minutes for 1km at 5km/h', () => {
    expect(estimatedWalkMinutes(1)).toBe(12)
  })

  it('returns 0 for 0km', () => {
    expect(estimatedWalkMinutes(0)).toBe(0)
  })
})
