import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { YieldGrid } from './YieldGrid'

const cells = [11, 15].flatMap((vb) =>
  [1, 2].map((t) => ({
    rule_set: 'ROLLING',
    k: 0,
    report_month: '2026-07-01',
    vb,
    t,
    sum_pay: 100 * t,
    sum_bal: 10000,
    n_ho: t === 2 && vb === 15 ? 3 : 24,
    yield: t / 100,
    keep: !(t === 2 && vb === 15),
    constrained: t === 2 && vb === 15 ? 0 : t / 100,
  })),
)

afterEach(() => vi.unstubAllGlobals())

describe('YieldGrid', () => {
  it('renders one block at a time with dropped cells flagged and switches k and rule set', async () => {
    const urls: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        urls.push(url)
        return new Response(JSON.stringify(cells), { status: 200, headers: { 'Content-Type': 'application/json' } })
      }),
    )
    const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } })
    render(
      <QueryClientProvider client={qc}>
        <YieldGrid runId="abc" cohorts={[11, 15]} nMonths={8} />
      </QueryClientProvider>,
    )
    expect((await screen.findAllByText('200')).length).toBe(2) // Σ payments block by default (t = 2, both VBs)
    await userEvent.click(screen.getByLabelText(/constrained yield/i))
    const dropped = screen.getAllByText('0', { selector: 'td' })[0]
    expect(dropped.closest('td')).toHaveClass('dropped')
    await userEvent.selectOptions(screen.getByLabelText(/^k$/i), '3')
    expect(urls.some((u) => u.includes('k=3'))).toBe(true)
    await userEvent.click(screen.getByLabelText(/VALUATION_CALC/i))
    expect(urls.some((u) => u.includes('rule_set=VALUATION_CALC'))).toBe(true)
  })
})
