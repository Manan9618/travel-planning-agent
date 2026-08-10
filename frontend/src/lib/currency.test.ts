import { describe, expect, it } from 'vitest'
import { formatCurrency } from './currency'

describe('formatCurrency', () => {
  it('formats USD with a dollar sign', () => {
    expect(formatCurrency(1850, 'USD')).toBe('$1,850')
  })

  it('formats EUR with a euro sign', () => {
    expect(formatCurrency(1850, 'EUR')).toBe('€1,850')
  })

  it('formats GBP with a pound sign', () => {
    expect(formatCurrency(1850, 'GBP')).toBe('£1,850')
  })

  it('rounds to whole units', () => {
    expect(formatCurrency(1850.67, 'USD')).toBe('$1,851')
  })

  it('falls back to a plain code-and-amount string for an invalid currency code', () => {
    expect(formatCurrency(100, 'NOT_A_CODE')).toBe('NOT_A_CODE 100')
  })
})
