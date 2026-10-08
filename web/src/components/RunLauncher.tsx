import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { ApiError } from '../api/client'
import { listRuns, startRun, type FitMode, type RunRequest } from '../api/curves'

const MODES: FitMode[] = ['THREE_PARAM', 'TWO_PARAM_FIXED_MU']

export function RunLauncher({ notice }: { notice?: string }) {
  const nav = useNavigate()
  const qc = useQueryClient()
  const [req, setReq] = useState<RunRequest>({
    report_month: '2026-07-01',
    preset: 'PARITY_JUL26',
    source: 'db',
    modes: ['THREE_PARAM', 'TWO_PARAM_FIXED_MU'],
  })
  const runs = useQuery({ queryKey: ['curve-runs'], queryFn: listRuns })
  const start = useMutation({
    mutationFn: startRun,
    onSuccess: (meta) => {
      qc.invalidateQueries({ queryKey: ['curve-runs'] })
      nav(`/curves?run=${meta.run_id}`)
    },
  })
  const toggle = (m: FitMode) =>
    setReq((r) => ({ ...r, modes: r.modes.includes(m) ? r.modes.filter((x) => x !== m) : [...r.modes, m] }))
  const err = start.error as ApiError | null
  return (
    <section className="card">
      <h2>Curve run</h2>
      {notice && <p className="warn">{notice}</p>}
      <form
        className="launcher"
        onSubmit={(e) => {
          e.preventDefault()
          start.mutate(req)
        }}
      >
        <label>
          Report month{' '}
          <input type="date" value={req.report_month} onChange={(e) => setReq({ ...req, report_month: e.target.value })} />
        </label>
        <label>
          Preset{' '}
          <select value={req.preset} onChange={(e) => setReq({ ...req, preset: e.target.value as RunRequest['preset'] })}>
            <option>PARITY_JUL26</option>
            <option>CORRECTED</option>
          </select>
        </label>
        <label>
          Source{' '}
          <select value={req.source} onChange={(e) => setReq({ ...req, source: e.target.value as RunRequest['source'] })}>
            <option value="db">Client database</option>
            <option value="fixtures">Workbook fixtures</option>
          </select>
        </label>
        <fieldset>
          <legend>Fit modes</legend>
          {MODES.map((m) => (
            <label key={m}>
              <input type="checkbox" checked={req.modes.includes(m)} onChange={() => toggle(m)} /> {m}
            </label>
          ))}
        </fieldset>
        <button type="submit" disabled={start.isPending || req.modes.length === 0}>
          {start.isPending ? 'Running…' : 'Start run'}
        </button>
        {err && <p className="bad">{err.detail ?? String(err)}</p>}
      </form>
      <h3>Previous runs (this server session)</h3>
      {runs.data && runs.data.length === 0 && <p>None yet.</p>}
      {runs.data && runs.data.length > 0 && (
        <table className="grid">
          <thead>
            <tr>
              <th>Run</th>
              <th>Report month</th>
              <th>Preset</th>
              <th>Source</th>
              <th>Fits</th>
            </tr>
          </thead>
          <tbody>
            {runs.data.map((r) => (
              <tr key={r.run_id} onClick={() => nav(`/curves?run=${r.run_id}`)} className="clickable">
                <td>{r.run_id}</td>
                <td>{r.report_month}</td>
                <td>{r.preset}</td>
                <td>{r.source}</td>
                <td>{r.n_fits}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
