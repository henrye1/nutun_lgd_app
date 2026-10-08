import { describe, expect, it } from 'vitest'
import { fmtInt, fmtPct, fmtRate, fmtYield } from './format'

describe('formats', () => {
  it('rates to 4 dp, pct to 2 dp, yields to 6 significant, blanks as dash', () => {
    expect(fmtRate(0.12345678)).toBe('0.1975')
    expect(fmtPct(0.0123456)).toBe('1.23%')
    expect(fmtYield(0.000123456789)).toBe('0.000123457')
    expect(fmtInt(55358)).toBe('55,358')
    expect(fmtRate(null)).toBe('—')
    expect(fmtYield(NaN)).toBe('—')
  })
})
