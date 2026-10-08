import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CurvesPage } from './CurvesPage'

vi.mock('react-plotly.js/factory', () => ({
  default: () => (p: { data: unknown[] }) => <div data-testid="plot" data-traces={p.data.length} />,
}))
vi.mock('plotly.js-dist-min', () => ({ default: {} }))

const summary = {
  run_id: 'abc',
  report_month: '2026-07-01',
  preset: 'PARITY_JUL26',
  source: 'fixtures',
  modes: ['THREE_PARAM', 'TWO_PARAM_FIXED_MU'],
  cohorts: [11, 15, 22, 23, 25, 44],
  n_months: 8,
  ma_window: 6,
  ma_fit_mode: 'TWO_PARAM_FIXED_MU',
  ma_members: { '11': [0, 1, 2, 3, 4, 5] },
  bounds_params_from: { '11': 'override ROLLING THREE_PARAM k=1' },
  n_fits: 102,
  n_not_fittable: 0,
  warnings: ['VB44 k=7: Warn = CHECK'],
  timings: { total: 0.7 },
  quirk_flags: {},
}

function mockApi(routes: Record<string, unknown>, status404: string[] = []) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const hdr = { headers: { 'Content-Type': 'application/json' } }
      if (status404.some((s) => url.includes(s))) return new Response(JSON.stringify({ detail: 'run not found' }), { status: 404, ...hdr })
      const key = Object.keys(routes).find((k) => url.includes(k))
      if (!key) return new Response('[]', { status: 200, ...hdr })
      return new Response(JSON.stringify(routes[key]), { status: 200, ...hdr })
    }),
  )
}

function renderAt(path: string) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <MemoryRouter initialEntries={[path]}>
        <Routes>
          <Route path="/curves" element={<CurvesPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('CurvesPage', () => {
  it('shows the launcher without a run and starts a run', async () => {
    mockApi({ '/api/curves/runs': [], '/api/curves/run': { run_id: 'abc', n_fits: 102 }, '/summary': summary })
    renderAt('/curves')
    expect(await screen.findByRole('button', { name: /start run/i })).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: /start run/i }))
    expect(await screen.findByText(/PARITY_JUL26/)).toBeInTheDocument()
    expect(screen.getByRole('tab', { name: /params/i })).toBeInTheDocument()
  })

  it('shows the launcher with a notice when the run id is stale', async () => {
    mockApi(
      { '/api/curves/runs': [{ run_id: 'old', report_month: '2026-07-01', preset: 'PARITY_JUL26', source: 'db', n_fits: 102 }] },
      ['/summary'],
    )
    renderAt('/curves?run=gone')
    expect(await screen.findByText(/no longer available/i)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /start run/i })).toBeInTheDocument()
    expect(await screen.findByText('old')).toBeInTheDocument()
  })

  it('renders the summary header and warnings badge for a live run', async () => {
    mockApi({ '/summary': summary })
    renderAt('/curves?run=abc')
    await waitFor(() => expect(screen.getByText(/2026-07-01/)).toBeInTheDocument())
    expect(screen.getByText('1 warning')).toBeInTheDocument()
    expect(screen.getAllByRole('tab')).toHaveLength(5)
  })
})
