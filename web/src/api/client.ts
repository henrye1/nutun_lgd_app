export class ApiError extends Error {
  status: number
  detail: string

  constructor(status: number, detail: string) {
    super(`HTTP ${status}: ${detail}`)
    this.status = status
    this.detail = detail
  }
}

async function parseError(r: Response, path: string): Promise<never> {
  let detail = `${path}: HTTP ${r.status}`
  try {
    const body = await r.json()
    if (body && typeof body.detail === 'string') detail = body.detail
  } catch {
    /* not JSON */
  }
  throw new ApiError(r.status, detail)
}

export async function fetchJson<T>(path: string): Promise<T> {
  const r = await fetch(path)
  if (!r.ok) return parseError(r, path)
  return (await r.json()) as T
}

export async function postJson<T>(path: string, body: unknown): Promise<T> {
  const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
  if (!r.ok) return parseError(r, path)
  return (await r.json()) as T
}

export interface DbStatus {
  configured: boolean
  server: string
  database: string
  auth: string
  reachable: boolean
  error: string
}

export interface ObjectStatus {
  name: string
  kind: string
  exists: boolean
  row_count: number | null
  modify_date: string | null
  missing_columns: string[]
  ok: boolean
  hint: string
}
