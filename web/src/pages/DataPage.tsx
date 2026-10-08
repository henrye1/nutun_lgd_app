import { useQuery } from '@tanstack/react-query'
import { fetchJson, type DbStatus, type ObjectStatus } from '../api/client'

const fmtInt = (n: number | null) => (n === null ? '—' : n.toLocaleString('en-GB'))
const fmtDate = (s: string | null) => (s ? s.slice(0, 16).replace('T', ' ') : '—')

export function DataPage() {
  const status = useQuery({ queryKey: ['db-status'], queryFn: () => fetchJson<DbStatus>('/api/db/status') })
  const objects = useQuery({
    queryKey: ['db-objects'],
    queryFn: () => fetchJson<ObjectStatus[]>('/api/db/objects'),
  })

  return (
    <section>
      <h1>Data &amp; Refresh</h1>
      <div className="card">
        {status.isLoading && <p>Checking connection…</p>}
        {status.data && (
          <p className={status.data.reachable ? 'ok' : 'bad'}>
            {status.data.reachable ? 'Connected' : 'Not connected'} — <span>{status.data.server}</span> /{' '}
            {status.data.database} ({status.data.auth} auth, read-only)
            {!status.data.reachable && status.data.error && (
              <>
                <br />
                <code>{status.data.error}</code>
              </>
            )}
          </p>
        )}
        {status.error && <p className="bad">{String(status.error)}</p>}
      </div>
      <h2>Required objects</h2>
      {objects.isLoading && <p>Loading objects…</p>}
      {objects.error && <p className="bad">Could not check the objects: {String(objects.error)}</p>}
      {objects.data && (
        <table className="grid">
          <thead>
            <tr>
              <th>Object</th>
              <th>Kind</th>
              <th>Rows</th>
              <th>Modified</th>
              <th>Status</th>
            </tr>
          </thead>
          <tbody>
            {objects.data.map((o) => (
              <tr key={o.name} className={o.ok ? 'ok' : o.exists ? 'warn' : 'missing'}>
                <td>{o.name}</td>
                <td>{o.kind}</td>
                <td className="num">{fmtInt(o.row_count)}</td>
                <td>{fmtDate(o.modify_date)}</td>
                <td>{o.ok ? 'OK' : o.exists ? o.hint : `Missing — ${o.hint}`}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  )
}
