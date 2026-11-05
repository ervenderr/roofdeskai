import { connection } from "next/server"
import { getBrief, isLive, requireTenantModule } from "@/lib/data"
import { when } from "@/lib/format"
import { metricEntries, sourceLabel, sourceStatus } from "@/lib/ops"

export default async function Brief() {
  if (!process.env.EXPORT) await connection()
  if (!isLive) {
    return (
      <>
        <h1>Daily brief</h1>
        <p className="sub">The daily brief is not available in the static demo.</p>
      </>
    )
  }
  await requireTenantModule("connectors")
  const { latest, runs } = await getBrief()
  return (
    <>
      <h1>Daily brief</h1>
      {!latest && <p className="sub">No brief yet.</p>}
      {latest && (
        <>
          <h2>Brief for {latest.local_date}</h2>
          <p className="sub">Figures come from the sources below. Sources marked mock data are sample figures.</p>
          <div className="card draft"><pre>{latest.text}</pre></div>
          {Array.isArray(latest.sources) && latest.sources.length > 0 && (
            <table>
              <thead><tr><th>Name</th><th>Data</th><th>Status</th><th>Metrics</th></tr></thead>
              <tbody>
                {latest.sources.map((s, i) => (
                  <tr key={i}>
                    <td>{s.name}</td>
                    <td>{sourceLabel(s.source)}</td>
                    <td>{s.ok ? sourceStatus(s) : <span className="pill escalated">{sourceStatus(s)}</span>}</td>
                    <td>{metricEntries(s.metrics).map(([k, v]) => `${k}: ${v}`).join(", ") || "-"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </>
      )}
      {runs.length > 0 && (
        <>
          <h2>Recent runs</h2>
          <ul>
            {runs.map((r) => (
              <li key={r.run_date}>{r.run_date} <span style={{ color: "var(--ink-3)", fontSize: 13 }}>{when(r.created_at)}</span></li>
            ))}
          </ul>
        </>
      )}
    </>
  )
}
