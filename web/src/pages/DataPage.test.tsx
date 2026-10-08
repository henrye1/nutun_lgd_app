import { render, screen } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { DataPage } from './DataPage'

const status = {
  configured: true,
  server: '192.168.0.55,1495',
  database: 'Nutun_Audit_2026_July26',
  auth: 'windows',
  reachable: true,
  error: '',
}
const objects = [
  {
    name: 'ACM_Payments',
    kind: 'table',
    exists: true,
    row_count: 55358,
    modify_date: '2026-08-01T10:00:00',
    missing_columns: [],
    ok: true,
    hint: '',
  },
  {
    name: 'fn_APP_Info',
    kind: 'function',
    exists: false,
    row_count: null,
    modify_date: null,
    missing_columns: [],
    ok: false,
    hint: 'Run sql/fn_APP_Info.sql in SSMS',
  },
]

function mockFetch(routes: Record<string, unknown>) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async (url: string) => {
      const key = Object.keys(routes).find((k) => url.includes(k))
      if (!key) return new Response('not found', { status: 404 })
      return new Response(JSON.stringify(routes[key]), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      })
    }),
  )
}

function renderPage() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  return render(
    <QueryClientProvider client={qc}>
      <DataPage />
    </QueryClientProvider>,
  )
}

afterEach(() => vi.unstubAllGlobals())

describe('DataPage', () => {
  it('shows connection status and lists objects, flagging missing ones with the SQL file to run', async () => {
    mockFetch({ '/api/db/status': status, '/api/db/objects': objects })
    renderPage()
    expect(await screen.findByText(/Connected/)).toBeInTheDocument()
    expect(screen.getByText('192.168.0.55,1495')).toBeInTheDocument()
    const row = (await screen.findByText('fn_APP_Info')).closest('tr')!
    expect(row).toHaveClass('missing')
    expect(row).toHaveTextContent('Run sql/fn_APP_Info.sql in SSMS')
    expect(screen.getByText('55,358')).toBeInTheDocument()
  })

  it('shows the error when the database is unreachable', async () => {
    mockFetch({
      '/api/db/status': { ...status, reachable: false, error: 'OperationalError: login timeout' },
      '/api/db/objects': [],
    })
    renderPage()
    expect(await screen.findByText(/Not connected/)).toBeInTheDocument()
    expect(screen.getByText(/login timeout/)).toBeInTheDocument()
  })
})
