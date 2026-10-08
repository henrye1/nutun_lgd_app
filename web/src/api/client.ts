export async function fetchJson<T>(path: string): Promise<T> {
  const r = await fetch(path)
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`)
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
