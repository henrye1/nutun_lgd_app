import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { ParamsGrid } from './ParamsGrid'

const row = (k: number, vb: number, mode: string, extra: Record<string, unknown> = {}) => ({
  k,
  'Report month': '2026-07',
  vb,
  m: 4.1234567,
  s: 1.5,
  cn: 0.2,
  mbound: 100,
  m_at_bound: 0,
  'K (fit points)': 55,
  'contiguous?': 'YES',
  'Sum count': 1540,
  'Weighted SSE': 2.2e-8,
  p: 3,
  df: 52,
  s_e: 2.06e-5,
  Mode: 7.37,
  Lifetime: 0.1096,
  'Rule 4': 'OK',
  Warn: '',
  mode,
  status: 'OK',
  reason: '',
  iterations: 40,
  start_used: 0,
  mu_source: '',
  grid: 'ROLLING',
  ...extra,
})
const rows = [
  row(0, 11, 'THREE_PARAM'),
  row(0, 11, 'TWO_PARAM_FIXED_MU', { Warn: 'CHECK' }),
  row(1, 15, 'THREE_PARAM', { status: 'NOT_FITTABLE', reason: 'only 3 kept points (needs 4)', m: null }),
  { ...row(0, 11, 'THREE_PARAM'), grid: 'VALUATION_CALC' },
]

function setup(onOpen = vi.fn()) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => new Response(JSON.stringify(rows), { status: 200, headers: { 'Content-Type': 'application/json' } })),
  )
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  render(
    <QueryClientProvider client={qc}>
      <ParamsGrid runId="abc" onOpen={onOpen} />
    </QueryClientProvider>,
  )
  return onOpen
}
afterEach(() => vi.unstubAllGlobals())

describe('ParamsGrid', () => {
  it('renders Params columns, flags CHECK and NOT_FITTABLE rows, opens a block on click', async () => {
    const onOpen = setup()
    expect((await screen.findAllByText('4.123457')).length).toBeGreaterThan(0)
    expect(screen.getAllByText('2.2000e-8').length).toBeGreaterThan(0)
    const check = screen.getAllByText('CHECK')[0].closest('tr')!
    expect(check).toHaveClass('warn')
    const nf = screen.getByText(/only 3 kept points/).closest('tr')!
    expect(nf).toHaveClass('missing')
    await userEvent.click(nf)
    expect(onOpen).toHaveBeenCalledWith('ROLLING', 1, 15, 'THREE_PARAM')
  })

  it('filters by grid and mode', async () => {
    setup()
    await screen.findAllByText('4.123457')
    expect(screen.getAllByRole('row')).toHaveLength(1 + 3) // ROLLING rows by default
    await userEvent.selectOptions(screen.getByLabelText(/grid/i), 'VALUATION_CALC')
    expect(screen.getAllByRole('row')).toHaveLength(1 + 1)
    await userEvent.selectOptions(screen.getByLabelText(/grid/i), 'ROLLING')
    await userEvent.selectOptions(screen.getByLabelText(/mode/i), 'TWO_PARAM_FIXED_MU')
    expect(screen.getAllByRole('row')).toHaveLength(1 + 1)
  })
})
