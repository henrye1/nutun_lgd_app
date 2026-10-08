import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { CurveSetTable } from './CurveSetTable'

const rows = [11, 15].flatMap((vb) =>
  Array.from({ length: 150 }, (_, i) => ({
    vb, t: i + 1, curve: 0.001, lb: vb === 11 && i < 2 ? 0.0005 : null, ub: vb === 11 && i < 2 ? 0.002 : null,
  })),
)
afterEach(() => vi.unstubAllGlobals())

describe('CurveSetTable', () => {
  it('renders the paste-block layout with blanks, limits rows, links the CSV export', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn(async () => new Response(JSON.stringify(rows), { status: 200, headers: { 'Content-Type': 'application/json' } })),
    )
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={qc}>
        <CurveSetTable runId="abc" cohorts={[11, 15]} />
      </QueryClientProvider>,
    )
    const headers = (await screen.findAllByRole('columnheader')).map((h) => h.textContent)
    expect(headers).toEqual(['t', '11', '15', 'UB 11', 'UB 15', 'LB 11', 'LB 15'])
    expect(screen.getAllByRole('row')).toHaveLength(1 + 120)
    await userEvent.click(screen.getByRole('button', { name: /show all/i }))
    expect(screen.getAllByRole('row')).toHaveLength(1 + 150)
    expect(screen.getByRole('link', { name: /export paste block/i })).toHaveAttribute('href', '/api/curves/abc/paste-block.csv')
    expect(screen.getAllByText('—').length).toBeGreaterThan(0)
  })
})
