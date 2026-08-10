import { describe, expect, it } from 'vitest'
import { destinationLabel } from './destinations'
import type { TravelPreferences } from '@/types/api'

function prefs(destination: string, additional_destinations: string[] = []): TravelPreferences {
  return {
    origin: null,
    destination,
    additional_destinations,
    start_date: null,
    end_date: null,
    duration_days: null,
    travelers: 1,
    budget_total: null,
    budget_currency: 'USD',
    budget_tier: null,
    trip_style: null,
    pace: 'moderate',
    interests: [],
    must_see: [],
    dietary_restrictions: [],
    accessibility_needs: [],
    priority_weights: {},
    raw_text: 't',
  }
}

describe('destinationLabel', () => {
  it('returns just the destination when there are no additional ones', () => {
    expect(destinationLabel(prefs('Paris'))).toBe('Paris')
  })

  it('joins two destinations with an ampersand', () => {
    expect(destinationLabel(prefs('Paris', ['Rome']))).toBe('Paris & Rome')
  })

  it('joins three or more destinations Oxford-comma style', () => {
    expect(destinationLabel(prefs('Paris', ['Rome', 'Florence']))).toBe('Paris, Rome & Florence')
  })
})
