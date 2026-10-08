import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CurveCharts } from './CurveCharts'

vi.mock('react-plotly.js/factory', () => ({
  default: () => (p: { data: Array<{ name: string }>; layout: { yaxis?: { type?: string } } }) => (
    <div data-testid="plot" data-traces={p.data.map((d) => d.name).join('|')} data-ytype={p.layout.yaxis?.type ?? 'linear'} />
  ),
}))
vi.mock('plotly.js-dist-min', () => ({ default: {} }))

const curves = [11, 15].flatMap((vb) =>
  [1, 2, 3].map((t) => ({ vb, t, curve: 0.001 * t, lb: vb === 11 ? 0.0005 * t : null, ub: vb === 11 ? 0.002 * t : null })),
)
const grid = [11, 15].flatMap((vb) =>
  [1, 2, 3].map((t) => ({
    rule_set: 'ROLLING', k: 0, report_month: '2026-07-01', vb, t, sum_pay: 1, sum_bal: 100, n_ho: 10,
    yield: 0.001 * t, keep: t !== 3, constrained: t !== 3 ? 0.001 * t : 0,
  })),
)
const params = [0, 1].flatMap((k) =>
  [11, 15].map((vb) => ({ k, vb, m: 4, s: 1.5, cn: 0.2, mode: 'TWO_PARAM_FIXED_MU', status: 'OK', grid: 'ROLLING' })),
)

afterEach(() => vi.unstubAllGlobals())

describe('CurveCharts', () => {
  it('draws dots, per-k fits, the MA curve and the band; omits the band when bounds are blank; toggles log scale', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        const json = (v: unknown) => new Response(JSON.stringify(v), { status: 200, headers: { 'Content-Type': 'application/json' } })
        if (url.includes('/grids')) return json(grid)
        if (url.includes('/params')) return json(params)
        if (url.endsWith('/curves')) return json(curves)
        return json([])
      }),
    )
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={qc}>
        <CurveCharts runId="abc" cohorts={[11, 15]} nMonths={2} maMembers={{ '11': [0, 1], '15': [0, 1] }} maFitMode="TWO_PARAM_FIXED_MU" />
      </QueryClientProvider>,
    )
    const plot = await screen.findByTestId('plot')
    await vi.waitFor(() => expect(screen.getByTestId('plot').getAttribute('data-traces')).toContain('fit k=1'))
    const names = screen.getByTestId('plot').getAttribute('data-traces')!.split('|')
    expect(names).toEqual(expect.arrayContaining(['kept', 'dropped', 'fit k=0', 'fit k=1', 'valuation curve', 'bounds']))
    expect(plot).toBeInTheDocument()
    await userEvent.selectOptions(screen.getByLabelText(/^vb$/i), '15')
    await vi.waitFor(() => expect(screen.getByTestId('plot').getAttribute('data-traces')).not.toContain('bounds'))
    await userEvent.click(screen.getByLabelText(/log scale/i))
    expect(screen.getByTestId('plot').getAttribute('data-ytype')).toBe('log')
  })
})
