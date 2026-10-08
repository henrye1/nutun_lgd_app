import { useQuery } from '@tanstack/react-query'
import { useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ApiError } from '../api/client'
import { getSummary, type FitMode, type RuleSet } from '../api/curves'
import { BlockDetail } from '../components/BlockDetail'
import { CurveCharts } from '../components/CurveCharts'
import { CurveSetTable } from '../components/CurveSetTable'
import { ParamsGrid } from '../components/ParamsGrid'
import { RunLauncher } from '../components/RunLauncher'
import { WarningsList } from '../components/WarningsList'
import { YieldGrid } from '../components/YieldGrid'

export type Tab = 'params' | 'grids' | 'block' | 'curves' | 'charts'
export interface BlockRef {
  grid: RuleSet
  k: number
  vb: number
  mode: FitMode
}
const TABS: Array<[Tab, string]> = [
  ['params', 'Params'],
  ['grids', 'Yield grids'],
  ['block', 'Block'],
  ['curves', 'Curves'],
  ['charts', 'Charts'],
]

export function CurvesPage() {
  const [sp, setSp] = useSearchParams()
  const runId = sp.get('run')
  const tab = (sp.get('tab') as Tab) || 'params'
  const [block, setBlock] = useState<BlockRef | null>(null)
  const summary = useQuery({
    queryKey: ['summary', runId],
    queryFn: () => getSummary(runId!),
    enabled: !!runId,
    retry: false,
  })
  const stale = !!runId && summary.error instanceof ApiError && summary.error.status === 404
  if (!runId || stale) {
    return (
      <RunLauncher
        notice={stale ? `Run ${runId} is no longer available (the server was restarted). Start a new run.` : undefined}
      />
    )
  }
  if (summary.isLoading) return <p>Loading run…</p>
  if (summary.error) return <p className="bad">{String(summary.error)}</p>
  const s = summary.data!
  const nWarn = s.warnings.length
  const openBlock = (b: BlockRef) => {
    setBlock(b)
    setSp({ run: s.run_id, tab: 'block' })
  }
  return (
    <section>
      <header className="runhead">
        <h1>Curve Workbench</h1>
        <span>
          Run <code>{s.run_id}</code> · {s.report_month} · {s.preset} · {s.source} · {s.n_fits} fits ({s.n_not_fittable} not
          fittable)
        </span>
        <span className={nWarn ? 'badge warn' : 'badge'}>
          {nWarn} warning{nWarn === 1 ? '' : 's'}
        </span>
      </header>
      <WarningsList warnings={s.warnings} />
      <nav role="tablist" className="tabs">
        {TABS.map(([id, label]) => (
          <button key={id} role="tab" aria-selected={tab === id} onClick={() => setSp({ run: s.run_id, tab: id })}>
            {label}
          </button>
        ))}
      </nav>
      <div role="tabpanel">
        {tab === 'params' && (
          <ParamsGrid runId={s.run_id} onOpen={(grid, k, vb, mode) => openBlock({ grid, k, vb, mode })} />
        )}
        {tab === 'grids' && <YieldGrid runId={s.run_id} cohorts={s.cohorts} nMonths={s.n_months} />}
        {tab === 'block' &&
          (block ? (
            <BlockDetail
              runId={s.run_id}
              block={block}
              boundsFrom={s.bounds_params_from}
              maFitMode={s.ma_fit_mode}
              onChanged={(_, next) => setBlock(next)}
            />
          ) : (
            <p>Pick a block on the Params tab.</p>
          ))}
        {tab === 'curves' && <CurveSetTable runId={s.run_id} cohorts={s.cohorts} />}
        {tab === 'charts' && (
          <CurveCharts runId={s.run_id} cohorts={s.cohorts} nMonths={s.n_months} maMembers={s.ma_members} maFitMode={s.ma_fit_mode} />
        )}
      </div>
    </section>
  )
}
