import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import { getParams, type FitMode, type ParamsRow, type RuleSet } from '../api/curves'
import { fmtNum } from '../format'

const expo = (v: unknown) => (v == null ? '—' : (v as number).toExponential(4))
const COLS: Array<[keyof ParamsRow, string, (v: unknown) => string]> = [
  ['k', 'k', String],
  ['Report month', 'Report month', String],
  ['vb', 'VB', String],
  ['m', 'm', (v) => fmtNum(v as number, 6)],
  ['s', 's', (v) => fmtNum(v as number, 6)],
  ['cn', 'cn', (v) => fmtNum(v as number, 6)],
  ['mbound', 'mbound', String],
  ['m_at_bound', 'm_at_bound', String],
  ['K (fit points)', 'K', String],
  ['contiguous?', 'contiguous?', String],
  ['Sum count', 'Σcount', String],
  ['Weighted SSE', 'SSE', expo],
  ['p', 'p', String],
  ['df', 'df', String],
  ['s_e', 's_e', expo],
  ['Mode', 'Mode', (v) => fmtNum(v as number, 4)],
  ['Lifetime', 'Lifetime', (v) => fmtNum(v as number, 4)],
  ['Rule 4', 'Rule 4', String],
  ['Warn', 'Warn', String],
  ['mode', 'mode', String],
  ['status', 'status', String],
]

export function ParamsGrid({
  runId,
  onOpen,
}: {
  runId: string
  onOpen: (grid: RuleSet, k: number, vb: number, mode: FitMode) => void
}) {
  const q = useQuery({ queryKey: ['params', runId], queryFn: () => getParams(runId) })
  const [grid, setGrid] = useState<RuleSet>('ROLLING')
  const [mode, setMode] = useState<FitMode | 'ALL'>('ALL')
  const [vb, setVb] = useState<number | 'ALL'>('ALL')
  const rows = useMemo(
    () =>
      (q.data ?? []).filter((r) => r.grid === grid && (mode === 'ALL' || r.mode === mode) && (vb === 'ALL' || r.vb === vb)),
    [q.data, grid, mode, vb],
  )
  const vbs = useMemo(() => Array.from(new Set((q.data ?? []).map((r) => r.vb))).sort((a, b) => a - b), [q.data])
  if (q.isLoading) return <p>Loading parameters…</p>
  if (q.error) return <p className="bad">{String(q.error)}</p>
  return (
    <div>
      <div className="filters">
        <label>
          Grid{' '}
          <select aria-label="grid" value={grid} onChange={(e) => setGrid(e.target.value as RuleSet)}>
            <option>ROLLING</option>
            <option>VALUATION_CALC</option>
          </select>
        </label>
        <label>
          Mode{' '}
          <select aria-label="mode" value={mode} onChange={(e) => setMode(e.target.value as FitMode | 'ALL')}>
            <option>ALL</option>
            <option>THREE_PARAM</option>
            <option>TWO_PARAM_FIXED_MU</option>
            <option>MANUAL</option>
          </select>
        </label>
        <label>
          VB{' '}
          <select
            aria-label="vb"
            value={String(vb)}
            onChange={(e) => setVb(e.target.value === 'ALL' ? 'ALL' : Number(e.target.value))}
          >
            <option>ALL</option>
            {vbs.map((v) => (
              <option key={v}>{v}</option>
            ))}
          </select>
        </label>
      </div>
      <table className="grid params">
        <thead>
          <tr>
            {COLS.map(([k, label]) => (
              <th key={String(k)}>{label}</th>
            ))}
            <th>reason</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((r) => (
            <tr
              key={`${r.grid}-${r.mode}-${r.k}-${r.vb}`}
              className={`clickable ${r.status === 'NOT_FITTABLE' ? 'missing' : r.Warn === 'CHECK' ? 'warn' : ''}`}
              onClick={() => onOpen(r.grid, r.k, r.vb, r.mode)}
            >
              {COLS.map(([k, , f]) => (
                <td key={String(k)} className="num">
                  {f(r[k])}
                </td>
              ))}
              <td>{r.reason}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
