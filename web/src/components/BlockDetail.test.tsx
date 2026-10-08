import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { BlockDetail } from './BlockDetail'

const fit = {
  k: 1, 'Report month': '2026-06', vb: 11, m: 4.57, s: 1.58, cn: 0.195, mbound: 100, m_at_bound: 0, 'K (fit points)': 54,
  'contiguous?': 'YES', 'Sum count': 1485, 'Weighted SSE': 2.1e-8, p: 3, df: 51, s_e: 2.0e-5, Mode: 7.3, Lifetime: 0.109,
  'Rule 4': 'OK', Warn: '', mode: 'THREE_PARAM', status: 'OK', reason: '', iterations: 60, start_used: 2, mu_source: '',
  grid: 'ROLLING',
}
const bounds = {
  vb: 11, k: 0, points: 'CONTIGUOUS_PREFIX', n_points: 55, p: 3, df: 52, sse: 2.2e-8, s_e: 2.06e-5, t_mult: 1.6747,
  V: [[1, 2, 3], [2, 4, 5], [3, 5, 6]], W: [[1, 0, 0], [0, 1, 0], [0, 0, 1]], P: [[4, 5], [5, 6]], Q: [[1, 0], [0, 1]],
  table: [{ t: 1, obs: 0.00075, keep: true, used: 1, w: 0.00065, z: -2.88, phi: 0.0039, pred: 0.00076, resid: -0.00001, x_m: -0.0014, x_s: 0.0035, x_cn: 0.0039, h3: 139.3, h2: 41.3, h: 139.3, sqrt_term: 40.98, se_i: 0.00084, half: 0.0014, lower: -0.00065, upper: 0.0022 }],
  warnings: [],
  sensitivity: { 'm-1%': 2.29e-8, 'm+1%': 2.31e-8, 's-1%': 2.21e-8, 's+1%': 2.22e-8, 'cn-1%': 2.23e-8, 'cn+1%': 2.22e-8 },
  params_from: 'override ROLLING THREE_PARAM k=1',
}
const summary = { run_id: 'abc', bounds_params_from: { '11': 'override ROLLING THREE_PARAM k=1' }, cohorts: [11], warnings: [], ma_members: { '11': [0] } }
const json = (v: unknown, status = 200) => new Response(JSON.stringify(v), { status, headers: { 'Content-Type': 'application/json' } })

function mock() {
  const bodies: unknown[] = []
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string, init?: RequestInit) => {
      if (init?.method === 'POST') {
        bodies.push(JSON.parse(String(init.body)))
        return json({ fit: { ...fit, mode: 'MANUAL', status: 'MANUAL', m: 4 }, summary })
      }
      if (url.includes('/fit/')) return json(fit)
      if (url.includes('/bounds/')) return json(bounds)
      if (url.includes('/summary')) return json(summary)
      return json([])
    }),
  )
  return bodies
}
afterEach(() => vi.unstubAllGlobals())

function setup(block = { grid: 'ROLLING' as const, k: 1, vb: 11, mode: 'THREE_PARAM' as const }) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  const onChanged = vi.fn()
  render(
    <QueryClientProvider client={qc}>
      <BlockDetail runId="abc" block={block} boundsFrom={{ '11': 'override ROLLING THREE_PARAM k=1' }} onChanged={onChanged} />
    </QueryClientProvider>,
  )
  return onChanged
}

describe('BlockDetail', () => {
  it('shows the parameter panel, the bounds t-table, matrices and sensitivity', async () => {
    mock()
    setup()
    expect(await screen.findByText('4.570000')).toBeInTheDocument() // m
    expect(await screen.findByText('CONTIGUOUS_PREFIX')).toBeInTheDocument()
    expect(screen.getByText('139.3000')).toBeInTheDocument() // h3
    expect(screen.getByText('m −1%')).toBeInTheDocument()
    expect(screen.getByText(/this block parameterises the VB11 bounds/i)).toBeInTheDocument()
  })

  it('refits as MANUAL with typed parameters and reports the change', async () => {
    const bodies = mock()
    const onChanged = setup()
    await screen.findByText('4.570000')
    await userEvent.selectOptions(screen.getByLabelText(/^mode$/i), 'MANUAL')
    await userEvent.clear(screen.getByLabelText(/^m$/i))
    await userEvent.type(screen.getByLabelText(/^m$/i), '4')
    await userEvent.clear(screen.getByLabelText(/^s$/i))
    await userEvent.type(screen.getByLabelText(/^s$/i), '1.5')
    await userEvent.clear(screen.getByLabelText(/^cn$/i))
    await userEvent.type(screen.getByLabelText(/^cn$/i), '0.2')
    await userEvent.click(screen.getByRole('button', { name: /fit block/i }))
    await waitFor(() => expect(onChanged).toHaveBeenCalled())
    expect(bodies[0]).toMatchObject({ grid: 'ROLLING', k: 1, vb: 11, mode: 'MANUAL', m: 4, s: 1.5, cn: 0.2 })
  })

  it('shows the reason for a NOT_FITTABLE block and the grid observations', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        if (url.includes('/fit/')) return json({ ...fit, status: 'NOT_FITTABLE', reason: 'only 3 kept points (needs 4)', m: null, s: null, cn: null })
        if (url.includes('/bounds/')) return json({ detail: 'no bounds for VB11' }, 404)
        return json([{ rule_set: 'ROLLING', k: 1, report_month: '2026-06-01', vb: 11, t: 1, sum_pay: 1, sum_bal: 100, n_ho: 3, yield: 0.01, keep: false, constrained: 0 }])
      }),
    )
    setup()
    expect(await screen.findByText(/only 3 kept points/)).toBeInTheDocument()
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
    expect(await screen.findByText('dropped')).toBeInTheDocument()
  })
})
