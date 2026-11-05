import { connection } from "next/server"
import { getCapacityFlags, isLive, requireTenantModule } from "@/lib/data"
import { when } from "@/lib/format"
import { FLAG_STATE_LABEL, FLAG_STATE_TONE, flagDetailParts, flagKindLabel, flagState, showAll } from "@/lib/ops"

export default async function Capacity({ searchParams }: { searchParams: Promise<{ all?: string }> }) {
  if (!process.env.EXPORT) await connection()
  if (!isLive) {
    return (
      <>
        <h1>Capacity</h1>
        <p className="sub">Capacity flags are not available in the static demo.</p>
      </>
    )
  }
  await requireTenantModule("capacity")
  const all = showAll((await searchParams).all)
  const flags = await getCapacityFlags(all)
  return (
    <>
      <h1>Capacity</h1>
      <p className="sub">Shifts that look over capacity, understaffed or under-used. Read only.</p>
      <p className="sub">
        {all ? "Showing all flags. " : "Showing open flags. "}
        {all ? <a href="/capacity">Show open flags only</a> : <a href="/capacity?all=1">Show all flags</a>}
      </p>
      {flags.length === 0 && <p className="sub">{all ? "No capacity flags yet." : "No open capacity flags."}</p>}
      {flags.length > 0 && (
        <table>
          <thead>
            <tr><th>Date</th><th>Shift</th><th>Issue</th><th>Details</th><th>State</th><th>First flagged</th></tr>
          </thead>
          <tbody>
            {flags.map((f) => {
              const st = flagState(f)
              const later = f.resolved_at ?? f.reflagged_at
              return (
                <tr key={f.flag_key}>
                  <td>{f.shift_date}</td>
                  <td>{f.shift_id}</td>
                  <td>{flagKindLabel(f.kind)}</td>
                  <td>{flagDetailParts(f.details).join(" · ") || "-"}</td>
                  <td>
                    <span className={`pill ${FLAG_STATE_TONE[st]}`}>{FLAG_STATE_LABEL[st]}</span>
                    {later && <div style={{ color: "var(--ink-3)", fontSize: 13 }}>{when(later)}</div>}
                  </td>
                  <td>{when(f.first_flagged_at)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      )}
    </>
  )
}
