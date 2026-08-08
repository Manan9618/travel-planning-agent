import { describe, expect, it } from 'vitest'
import { weatherCode } from './weatherCode'

describe('weatherCode', () => {
  it('maps known OpenWeatherMap conditions to METAR-style codes', () => {
    expect(weatherCode('Clear')).toBe('CLR')
    expect(weatherCode('Clouds')).toBe('OVC')
    expect(weatherCode('Rain')).toBe('RAIN')
    expect(weatherCode('Thunderstorm')).toBe('TSRA')
  })

  it('falls back to a truncated uppercase code for unknown conditions', () => {
    expect(weatherCode('Tornado')).toBe('TORN')
  })
})
