import { describe, expect, it } from 'vitest'
import { DAY_COLORS, dayColor } from './dayColors'

describe('dayColor', () => {
  it('maps day 1 to the first color', () => {
    expect(dayColor(1)).toBe(DAY_COLORS[0])
  })

  it('maps day 2 to the second color', () => {
    expect(dayColor(2)).toBe(DAY_COLORS[1])
  })

  it('wraps around after the palette is exhausted', () => {
    expect(dayColor(DAY_COLORS.length + 1)).toBe(DAY_COLORS[0])
  })
})
