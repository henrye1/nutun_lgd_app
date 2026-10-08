import { fetchJson, postJson } from './client'

export type FitMode = 'THREE_PARAM' | 'TWO_PARAM_FIXED_MU' | 'MANUAL'
export type RuleSet = 'ROLLING' | 'VALUATION_CALC'

export interface RunRequest {
  report_month: string
  preset: 'PARITY_JUL26' | 'CORRECTED'
  source: 'db' | 'fixtures'
  modes: FitMode[]
}

export interface RunMeta {
  run_id: string
  report_month: string
  preset: string
  source: string
  n_fits: number
  n_not_fittable: number
  warnings: string[]
  timings: Record<string, number>
}

export interface RunSummary extends RunMeta {
  modes: FitMode[]
  cohorts: number[]
  n_months: number
  ma_window: number
  ma_fit_mode: FitMode
  ma_members: Record<string, number[]>
  bounds_params_from: Record<string, string>
  quirk_flags: Record<string, string>
}

export interface ParamsRow {
  k: number
  'Report month': string
  vb: number
  m: number | null
  s: number | null
  cn: number | null
  mbound: number
  m_at_bound: number
  'K (fit points)': number
  'contiguous?': string
  'Sum count': number
  'Weighted SSE': number | null
  p: number
  df: number
  s_e: number | null
  Mode: number | null
  Lifetime: number | null
  'Rule 4': string
  Warn: string
  mode: FitMode
  status: string
  reason: string
  iterations: number
  start_used: number
  mu_source: string
  grid: RuleSet
}
export type FitRow = ParamsRow

export interface GridRow {
  rule_set: RuleSet
  k: number
  report_month: string
  vb: number
  t: number
  sum_pay: number
  sum_bal: number
  n_ho: number
  yield: number | null
  keep: boolean
  constrained: number
}

export interface CurveRow {
  vb: number
  t: number
  curve: number | null
  lb: number | null
  ub: number | null
}

export interface BoundsTableRow {
  t: number
  obs: number
  keep: boolean
  used: number
  w: number
  z: number
  phi: number
  pred: number
  resid: number
  x_m: number
  x_s: number
  x_cn: number
  h3: number
  h2: number
  h: number
  sqrt_term: number
  se_i: number | null
  half: number | null
  lower: number | null
  upper: number | null
}

export interface BoundsPayload {
  vb: number
  k: number
  points: string
  n_points: number
  p: number
  df: number
  sse: number
  s_e: number | null
  t_mult: number | null
  V: number[][]
  W: number[][]
  P: number[][]
  Q: number[][]
  table: BoundsTableRow[]
  warnings: string[]
  sensitivity: Record<string, number>
  params_from: string
}

export interface RefitRequest {
  grid: RuleSet
  k: number
  vb: number
  mode: FitMode
  mu?: number | null
  m?: number | null
  s?: number | null
  cn?: number | null
}

export const startRun = (req: RunRequest) => postJson<RunMeta>('/api/curves/run', req)
export const listRuns = () => fetchJson<RunMeta[]>('/api/curves/runs')
export const getSummary = (id: string) => fetchJson<RunSummary>(`/api/curves/${id}/summary`)
export const getParams = (id: string) => fetchJson<ParamsRow[]>(`/api/curves/${id}/params`)
export const getGrid = (id: string, ruleSet: RuleSet, k: number) =>
  fetchJson<GridRow[]>(`/api/curves/${id}/grids?rule_set=${ruleSet}&k=${k}`)
export const getCurves = (id: string) => fetchJson<CurveRow[]>(`/api/curves/${id}/curves`)
export const getBounds = (id: string, vb: number) => fetchJson<BoundsPayload>(`/api/curves/${id}/bounds/${vb}`)
export const getFit = (id: string, mode: FitMode, k: number, vb: number, grid: RuleSet = 'ROLLING') =>
  fetchJson<FitRow>(`/api/curves/${id}/fit/${mode}/${k}/${vb}?grid=${grid}`)
export const refit = (id: string, body: RefitRequest) =>
  postJson<{ fit: FitRow; summary: RunSummary }>(`/api/curves/${id}/refit`, body)
export const pasteBlockUrl = (id: string) => `/api/curves/${id}/paste-block.csv`
