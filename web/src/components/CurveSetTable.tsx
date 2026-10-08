import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { getCurves, pasteBlockUrl } from '../api/curves'
import { fmtYield } from '../format'

type Cell = { curve: number | null; lb: number | null; ub: number | null }

export function CurveSetTable({ runId, cohorts }: { runId: string; cohorts: number[] }) {
  const q = useQuery({ queryKey: ['curves', runId], queryFn: () => getCurves(runId) })
  const [all, setAll] = useState(false)
  if (q.isLoading) return <p>Loading curves…</p>
  const byT = new Map<number, Map<number, Cell>>()
  for (const r of q.data ?? []) {
    if (!byT.has(r.t)) byT.set(r.t, new Map())
    byT.get(r.t)!.set(r.vb, r)
  }
  const ts = Array.from(byT.keys()).sort((a, b) => a - b)
  const shown = all ? ts : ts.slice(0, 120)
  return (
    <div>
      <p>
        <a href={pasteBlockUrl(runId)} download>
          Export paste block (Curves!A3:S503)
        </a>{' '}
        · {ts.length} rows
        {!all && ts.length > 120 && (
          <>
            {' '}
            ·{' '}
            <button type="button" onClick={() => setAll(true)}>
              Show all
            </button>
          </>
        )}
      </p>
      <table className="grid curveset">
        <thead>
          <tr>
            <th>t</th>
            {cohorts.map((vb) => (
              <th key={`c${vb}`}>{vb}</th>
            ))}
            {cohorts.map((vb) => (
              <th key={`u${vb}`}>UB {vb}</th>
            ))}
            {cohorts.map((vb) => (
              <th key={`l${vb}`}>LB {vb}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {shown.map((t) => {
            const row = byT.get(t)!
            return (
              <tr key={t}>
                <td>{t}</td>
                {cohorts.map((vb) => (
                  <td key={`c${vb}`} className="num">
                    {fmtYield(row.get(vb)?.curve)}
                  </td>
                ))}
                {cohorts.map((vb) => (
                  <td key={`u${vb}`} className="num">
                    {fmtYield(row.get(vb)?.ub)}
                  </td>
                ))}
                {cohorts.map((vb) => (
                  <td key={`l${vb}`} className="num">
                    {fmtYield(row.get(vb)?.lb)}
                  </td>
                ))}
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
