import { afterEach, describe, expect, it, vi } from 'vitest'
import { ApiError, postJson } from './client'
import { getGrid, pasteBlockUrl, refit, startRun } from './curves'

afterEach(() => vi.unstubAllGlobals())

const json = (v: unknown, status = 200) =>
  new Response(JSON.stringify(v), { status, headers: { 'Content-Type': 'application/json' } })

describe('curves api', () => {
  it('posts a run request and returns the meta', async () => {
    const calls: Array<[string, RequestInit | undefined]> = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string, init?: RequestInit) => {
        calls.push([url, init])
        return json({ run_id: 'abc', n_fits: 102 })
      }),
    )
    const r = await startRun({ report_month: '2026-07-01', preset: 'PARITY_JUL26', source: 'fixtures', modes: ['THREE_PARAM'] })
    expect(r.run_id).toBe('abc')
    expect(calls[0][0]).toBe('/api/curves/run')
    expect(JSON.parse(String(calls[0][1]?.body)).preset).toBe('PARITY_JUL26')
  })

  it('builds grid and paste urls and surfaces API errors with detail', async () => {
    const urls: string[] = []
    vi.stubGlobal(
      'fetch',
      vi.fn(async (url: string) => {
        urls.push(url)
        if (url.includes('/grids')) return json([])
        return json({ detail: 'MANUAL mode needs m, s and cn' }, 422)
      }),
    )
    await getGrid('abc', 'ROLLING', 3)
    expect(urls[0]).toBe('/api/curves/abc/grids?rule_set=ROLLING&k=3')
    expect(pasteBlockUrl('abc')).toBe('/api/curves/abc/paste-block.csv')
    await expect(refit('abc', { grid: 'ROLLING', k: 0, vb: 11, mode: 'MANUAL', m: 4 })).rejects.toMatchObject({
      status: 422,
      detail: 'MANUAL mode needs m, s and cn',
    })
    await expect(postJson('/x', {})).rejects.toBeInstanceOf(ApiError)
  })
})
