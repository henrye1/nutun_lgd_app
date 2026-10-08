import { useQuery } from '@tanstack/react-query'
import { useMemo, useState } from 'react'
import Plotly from 'plotly.js-dist-min'
import createPlotlyComponent from 'react-plotly.js/factory'
import { getCurves, getGrid, getParams, type FitMode } from '../api/curves'
import { lognormal } from '../lognormal'

const Plot = createPlotlyComponent(Plotly)
const T120 = Array.from({ length: 120 }, (_, i) => i + 1)

export function CurveCharts({
  runId,
  cohorts,
  nMonths,
  maMembers,
  maFitMode,
}: {
  runId: string
  cohorts: number[]
  nMonths: number
  maMembers: Record<string, number[]>
  maFitMode: FitMode
}) {
  const [vb, setVb] = useState(cohorts[0])
  const [k, setK] = useState(0)
  const [log, setLog] = useState(false)
  const curves = useQuery({ queryKey: ['curves', runId], queryFn: () => getCurves(runId) })
  const grid = useQuery({ queryKey: ['grid', runId, 'ROLLING', k], queryFn: () => getGrid(runId, 'ROLLING', k) })
  const params = useQuery({ queryKey: ['params', runId], queryFn: () => getParams(runId) })
  const data = useMemo(() => {
    const out: Array<Record<string, unknown>> = []
    const g = (grid.data ?? []).filter((r) => r.vb === vb)
    const kept = g.filter((r) => r.keep)
    const dropped = g.filter((r) => !r.keep)
    out.push({ name: 'kept', type: 'scatter', mode: 'markers', x: kept.map((r) => r.t), y: kept.map((r) => r.yield), marker: { color: '#15314b', size: 7 } })
    out.push({ name: 'dropped', type: 'scatter', mode: 'markers', x: dropped.map((r) => r.t), y: dropped.map((r) => r.yield), marker: { color: '#15314b', size: 7, symbol: 'circle-open' } })
    for (const kk of maMembers[String(vb)] ?? []) {
      const p = (params.data ?? []).find((r) => r.grid === 'ROLLING' && r.mode === maFitMode && r.k === kk && r.vb === vb)
      if (p && p.m != null && p.s != null && p.cn != null) {
        const { m, s, cn } = p
        out.push({ name: `fit k=${kk}`, type: 'scatter', mode: 'lines', x: T120, y: T120.map((x) => lognormal(x, m, s, cn)), line: { width: 1, color: '#9ca3af' } })
      }
    }
    const c = (curves.data ?? []).filter((r) => r.vb === vb)
    out.push({ name: 'valuation curve', type: 'scatter', mode: 'lines', x: c.map((r) => r.t), y: c.map((r) => r.curve), line: { width: 3, color: '#b42318' } })
    const band = c.filter((r) => r.lb != null && r.ub != null)
    if (band.length) {
      out.push({
        name: 'bounds', type: 'scatter', mode: 'lines', fill: 'toself', fillcolor: 'rgba(21,49,75,0.12)', line: { width: 0 },
        x: [...band.map((r) => r.t), ...band.map((r) => r.t).reverse()],
        y: [...band.map((r) => r.ub), ...band.map((r) => r.lb).reverse()],
      })
    }
    return out
  }, [grid.data, curves.data, params.data, vb, maMembers, maFitMode])
  return (
    <div>
      <div className="filters">
        <label>
          VB{' '}
          <select aria-label="vb" value={vb} onChange={(e) => setVb(Number(e.target.value))}>
            {cohorts.map((v) => (
              <option key={v} value={v}>
                {v}
              </option>
            ))}
          </select>
        </label>
        <label>
          observed k{' '}
          <select aria-label="observed k" value={k} onChange={(e) => setK(Number(e.target.value))}>
            {Array.from({ length: nMonths }, (_, i) => (
              <option key={i} value={i}>
                {i}
              </option>
            ))}
          </select>
        </label>
        <label>
          <input type="checkbox" checked={log} onChange={(e) => setLog(e.target.checked)} /> log scale
        </label>
      </div>
      <Plot
        data={data as never}
        layout={{
          title: { text: `VB${vb}: observed yields, fitted curves, valuation curve and bounds` },
          xaxis: { title: { text: 'month on book (t)' }, range: [0, 121] },
          yaxis: { title: { text: 'yield' }, type: log ? 'log' : 'linear' },
          height: 480,
          margin: { t: 40 },
        }}
        useResizeHandler
        style={{ width: '100%' }}
      />
    </div>
  )
}
