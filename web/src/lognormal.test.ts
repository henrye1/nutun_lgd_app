import { describe, expect, it } from 'vitest'
import { lognormal } from './lognormal'

describe('lognormal', () => {
  it('matches the sheet formula cn·exp(−z²/2)/(t·s·√2π)', () => {
    const m = 4
    const s = 1.7
    const cn = 0.3
    const t = 10
    const z = (Math.log(t) - m) / s
    expect(lognormal(t, m, s, cn)).toBeCloseTo((cn * Math.exp((-z * z) / 2)) / (t * s * Math.sqrt(2 * Math.PI)), 15)
  })
})
