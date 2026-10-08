import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { getGrid, type GridRow, type RuleSet } from '../api/curves'
import { fmtInt, fmtYield } from '../format'

type Block = 'sum_pay' | 'sum_bal' | 'yield' | 'n_ho' | 'keep' | 'constrained'
const BLOCKS: Array<[Block, string]> = [
  ['sum_pay', 'Σ FLI-adj payments'],
  ['sum_bal', 'Σ balance'],
  ['yield', 'Raw yield'],
  ['n_ho', 'nHO'],
  ['keep', 'Keep'],
  ['constrained', 'Constrained yield'],
]

function cell(r: GridRow, b: Block): string {
  if (b === 'keep') return r.keep ? 'KEPT' : 'dropped'
  if (b === 'n_ho') return fmtInt(r.n_ho)
  if (b === 'sum_pay' || b === 'sum_bal') return r[b].toLocaleString('en-GB', { maximumFractionDigits: 2 })
  return fmtYield(r[b])
}

export function YieldGrid({ runId, cohorts, nMonths }: { runId: string; cohorts: number[]; nMonths: number }) {
  const [ruleSet, setRuleSet] = useState<RuleSet>('ROLLING')
  const [k, setK] = useState(0)
  const [block, setBlock] = useState<Block>('sum_pay')
  const q = useQuery({
    queryKey: ['grid', runId, ruleSet, ruleSet === 'ROLLING' ? k : 0],
    queryFn: () => getGrid(runId, ruleSet, ruleSet === 'ROLLING' ? k : 0),
  })
  const byT = new Map<number, Map<number, GridRow>>()
  for (const r of q.data ?? []) {
    if (!byT.has(r.t)) byT.set(r.t, new Map())
    byT.get(r.t)!.set(r.vb, r)
  }
  const ts = Array.from(byT.keys()).sort((a, b) => a - b)
  return (
    <div>
      <div className="filters">
        <label>
          <input type="radio" name="rs" checked={ruleSet === 'ROLLING'} onChange={() => setRuleSet('ROLLING')} /> ROLLING
        </label>
        <label>
          <input type="radio" name="rs" checked={ruleSet === 'VALUATION_CALC'} onChange={() => setRuleSet('VALUATION_CALC')} />{' '}
          VALUATION_CALC
        </label>
        {ruleSet === 'ROLLING' && (
          <label>
            k{' '}
            <select aria-label="k" value={k} onChange={(e) => setK(Number(e.target.value))}>
              {Array.from({ length: nMonths }, (_, i) => (
                <option key={i} value={i}>
                  {i}
                </option>
              ))}
            </select>
          </label>
        )}
        <fieldset className="inline">
          <legend>Block</legend>
          {BLOCKS.map(([b, label]) => (
            <label key={b}>
              <input type="radio" name="block" checked={block === b} onChange={() => setBlock(b)} /> {label}
            </label>
          ))}
        </fieldset>
      </div>
      {q.isLoading && <p>Loading grid…</p>}
      {q.data && (
        <table className="grid yields">
          <thead>
            <tr>
              <th>t</th>
              {cohorts.map((vb) => (
                <th key={vb}>{vb}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {ts.map((t) => (
              <tr key={t}>
                <td>{t}</td>
                {cohorts.map((vb) => {
                  const r = byT.get(t)!.get(vb)
                  return (
                    <td key={vb} className={`num ${r && !r.keep ? 'dropped' : ''}`}>
                      {r ? cell(r, block) : '—'}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}
