import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { ApiError } from '../api/client'
import { getBounds, getFit, getGrid, refit, type BoundsPayload, type FitMode, type RuleSet, type RunSummary } from '../api/curves'
import { fmtNum, fmtYield } from '../format'

export interface BlockRef {
  grid: RuleSet
  k: number
  vb: number
  mode: FitMode
}

const expo = (v: number | null | undefined) => (v == null || Number.isNaN(v) ? '—' : v.toExponential(4))
const SENS: Array<[string, string]> = [
  ['m-1%', 'm −1%'],
  ['m+1%', 'm +1%'],
  ['s-1%', 's −1%'],
  ['s+1%', 's +1%'],
  ['cn-1%', 'cn −1%'],
  ['cn+1%', 'cn +1%'],
]
type TRow = BoundsPayload['table'][number]
const TCOLS: Array<[keyof TRow, string]> = [
  ['t', 't'], ['obs', 'obs'], ['keep', 'keep'], ['used', 'used'], ['w', 'w'], ['z', 'z'], ['phi', 'phi'], ['pred', 'pred'],
  ['resid', 'resid'], ['x_m', 'x_m'], ['x_s', 'x_s'], ['x_cn', 'x_cn'], ['h3', 'h 3-param'], ['h2', 'h 2-param'],
  ['h', 'h used'], ['sqrt_term', 'SQRT(1/w+h)'], ['se_i', 'se_i'], ['half', 'half-width'], ['lower', 'LOWER'], ['upper', 'UPPER'],
]

function tcell(k: keyof TRow, v: TRow[keyof TRow]): string {
  if (typeof v === 'boolean') return v ? 'KEPT' : 'dropped'
  if (k === 't' || k === 'used') return String(v)
  if (v == null) return '—'
  return Math.abs(v) >= 1 ? fmtNum(v, 4) : fmtYield(v)
}

function Matrix({ title, m }: { title: string; m: number[][] }) {
  return (
    <table className="grid matrix">
      <caption>{title}</caption>
      <tbody>
        {m.map((row, i) => (
          <tr key={i}>
            {row.map((v, j) => (
              <td key={j} className="num">
                {expo(v)}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  )
}

export function BlockDetail({
  runId,
  block: blockProp,
  boundsFrom,
  maFitMode,
  onChanged,
}: {
  runId: string
  block: BlockRef
  boundsFrom: Record<string, string>
  maFitMode: FitMode
  onChanged: (s: RunSummary, block: BlockRef) => void
}) {
  const qc = useQueryClient()
  // the block being shown; after a refit it follows the new mode so the result is what the panel shows
  const [block, setBlockState] = useState<BlockRef>(blockProp)
  useEffect(() => setBlockState(blockProp), [blockProp])
  const fitQ = useQuery({ queryKey: ['fit', runId, block], queryFn: () => getFit(runId, block.mode, block.k, block.vb, block.grid) })
  const from = boundsFrom[String(block.vb)] ?? ''
  const feedsBounds = from.includes(block.grid === 'ROLLING' ? `ROLLING ${block.mode} k=${block.k}` : `VALUATION_CALC ${block.mode}`)
  const boundsQ = useQuery({
    queryKey: ['bounds', runId, block.vb],
    queryFn: () => getBounds(runId, block.vb),
    enabled: feedsBounds,
    retry: false,
  })
  const gridQ = useQuery({
    queryKey: ['grid', runId, block.grid, block.grid === 'ROLLING' ? block.k : 0],
    queryFn: () => getGrid(runId, block.grid, block.grid === 'ROLLING' ? block.k : 0),
    enabled: !feedsBounds || boundsQ.isError,
  })
  const [mode, setMode] = useState<FitMode>(block.mode)
  const [mu, setMu] = useState('')
  const [m, setM] = useState('')
  const [s, setS] = useState('')
  const [cn, setCn] = useState('')
  useEffect(() => setMode(block.mode), [block])
  useEffect(() => {
    const f = fitQ.data
    if (!f) return
    setM(f.m == null ? '' : String(f.m))
    setS(f.s == null ? '' : String(f.s))
    setCn(f.cn == null ? '' : String(f.cn))
    if (f.mode === 'TWO_PARAM_FIXED_MU' && f.m != null) setMu(String(f.m))
  }, [fitQ.data])
  const doRefit = useMutation({
    mutationFn: (nextMode: FitMode) =>
      refit(runId, {
        grid: block.grid,
        k: block.k,
        vb: block.vb,
        mode: nextMode,
        mu: nextMode === 'TWO_PARAM_FIXED_MU' && mu.trim() !== '' ? Number(mu) : null, // null → the run's μ table
        m: nextMode === 'MANUAL' ? Number(m) : null,
        s: nextMode === 'MANUAL' ? Number(s) : null,
        cn: nextMode === 'MANUAL' ? Number(cn) : null,
      }),
    onSuccess: (res) => {
      const next: BlockRef = { ...block, mode: res.fit.mode }
      for (const key of ['params', 'curves', 'bounds', 'summary']) qc.invalidateQueries({ queryKey: [key, runId] })
      qc.setQueryData(['fit', runId, next], res.fit)
      setBlockState(next)
      onChanged(res.summary, next)
    },
  })
  const f = fitQ.data
  const err = doRefit.error as ApiError | null
  const num = (v: string) => (v.trim() === '' ? NaN : Number(v))
  const manualOk = Number.isFinite(num(m)) && num(s) > 1e-4 && num(cn) > 1e-9
  const canFit = mode !== 'MANUAL' || manualOk
  const b = boundsQ.data
  const title = `VB${block.vb} · ${block.grid === 'ROLLING' ? `k = ${block.k}` : 'VALUATION_CALC'} · ${block.mode}`
  const panel: Array<[string, string]> = f
    ? [
        ['m (location)', fmtNum(f.m, 6)], ['s (shape)', fmtNum(f.s, 6)], ['cn (scale)', fmtNum(f.cn, 6)], ['mbound', String(f.mbound)],
        ['m_at_bound', String(f.m_at_bound)], ['K (fit points)', String(f['K (fit points)'])], ['contiguous?', f['contiguous?']],
        ['Σ count', String(f['Sum count'])], ['Weighted SSE', expo(f['Weighted SSE'])], ['p', String(f.p)], ['df', String(f.df)],
        ['s_e', expo(f.s_e)], ['Mode', fmtNum(f.Mode, 4)], ['Lifetime', fmtNum(f.Lifetime, 4)], ['Rule 4', f['Rule 4']],
        ['Warn', f.Warn || '—'], ['status', f.status], ['reason', f.reason || '—'], ['μ source', f.mu_source || '—'],
        ['iterations', String(f.iterations)], ['start used', String(f.start_used)],
      ]
    : []
  return (
    <div className="block">
      <h2>{title}</h2>
      {fitQ.isLoading && <p>Loading block…</p>}
      {f && (
        <div className="panel-row">
          <table className="grid panel">
            <tbody>
              {panel.map(([k, v]) => (
                <tr key={k}>
                  <th>{k}</th>
                  <td className="num">{v}</td>
                </tr>
              ))}
            </tbody>
          </table>
          <form
            className="refit card"
            onSubmit={(e) => {
              e.preventDefault()
              doRefit.mutate(mode)
            }}
          >
            <h3>Refit this block</h3>
            <label>
              mode{' '}
              <select aria-label="mode" value={mode} onChange={(e) => setMode(e.target.value as FitMode)}>
                <option>THREE_PARAM</option>
                <option>TWO_PARAM_FIXED_MU</option>
                <option>MANUAL</option>
              </select>
            </label>
            {mode === 'TWO_PARAM_FIXED_MU' && (
              <label>
                μ <input aria-label="mu" value={mu} onChange={(e) => setMu(e.target.value)} />
              </label>
            )}
            {mode === 'MANUAL' && (
              <>
                <label>
                  m <input aria-label="m" value={m} onChange={(e) => setM(e.target.value)} />
                </label>
                <label>
                  s <input aria-label="s" value={s} onChange={(e) => setS(e.target.value)} />
                </label>
                <label>
                  cn <input aria-label="cn" value={cn} onChange={(e) => setCn(e.target.value)} />
                </label>
              </>
            )}
            <button type="submit" disabled={doRefit.isPending || !canFit}>
              Fit block
            </button>
            <button
              type="button"
              onClick={() => {
                setMode(blockProp.mode)
                setMu('')
                doRefit.mutate(blockProp.mode)
              }}
              disabled={doRefit.isPending}
            >
              Reset to run
            </button>
            {err && <p className="bad">{err.detail ?? String(err)}</p>}
            {feedsBounds && <p className="note">This block parameterises the VB{block.vb} bounds ({from}).</p>}
            <p className="note">
              The valuation curve uses {maFitMode} fits; a refit in another mode adds a parallel fit (see the Params
              tab) and does not move the curve or the bounds unless that mode is the one the run reads.
            </p>
          </form>
        </div>
      )}
      {b && (
        <>
          <p>
            Prediction limits: {b.points} · n = {b.n_points} · p = {b.p} · df = {b.df} · SSE {expo(b.sse)} · s_e {expo(b.s_e)} ·
            t = {fmtNum(b.t_mult, 4)}
          </p>
          <div className="panel-row">
            <Matrix title="X'WX (V)" m={b.V} />
            <Matrix title="Inverse (W)" m={b.W} />
            <Matrix title="P (s, cn)" m={b.P} />
            <Matrix title="Q = P⁻¹" m={b.Q} />
            <table className="grid panel">
              <caption>Sensitivity: SSE at ±1%</caption>
              <tbody>
                {SENS.map(([k, label]) => (
                  <tr key={k}>
                    <th>{label}</th>
                    <td className="num">{expo(b.sensitivity[k])}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <table className="grid ttable">
            <thead>
              <tr>
                {TCOLS.map(([k, l]) => (
                  <th key={String(k)}>{l}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {b.table.map((r) => (
                <tr key={r.t} className={r.used ? '' : 'dropped'}>
                  {TCOLS.map(([k]) => (
                    <td key={String(k)} className="num">
                      {tcell(k, r[k])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </>
      )}
      {!b && gridQ.data && (
        <table className="grid ttable">
          <thead>
            <tr>
              <th>t</th>
              <th>obs (constrained yield)</th>
              <th>keep</th>
              <th>nHO</th>
            </tr>
          </thead>
          <tbody>
            {gridQ.data
              .filter((r) => r.vb === block.vb)
              .map((r) => (
                <tr key={r.t} className={r.keep ? '' : 'dropped'}>
                  <td>{r.t}</td>
                  <td className="num">{fmtYield(r.constrained)}</td>
                  <td>{r.keep ? 'KEPT' : 'dropped'}</td>
                  <td className="num">{r.n_ho}</td>
                </tr>
              ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
