import { connection } from "next/server"
import Link from "next/link"
import { getConversations } from "@/lib/data"
import { OUTCOME_LABEL, duration, when } from "@/lib/format"


export default async function Conversations() {
  if (!process.env.EXPORT) await connection() // normal builds render per request; the static export (EXPORT=1) prerenders the snapshot
  const rows = await getConversations()
  return (
    <>
      <h1>Conversations</h1>
      <p className="sub">Newest first. Open one to see the transcript with tool calls inline.</p>
      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table>
          <thead><tr><th>#</th><th>Started</th><th>Channel</th><th>Outcome</th><th className="num">Duration</th><th className="num">Model calls</th><th className="num">Cost</th></tr></thead>
          <tbody>
            {rows.map((c) => {
              const outcome = c.outcome ?? "open"
              return (
                <tr key={c.id}>
                  <td><Link href={`/conversations/${c.id}`}>{c.id}</Link></td>
                  <td>{when(c.started_at)}</td>
                  <td>{c.channel}</td>
                  <td><span className={`pill ${outcome === "open" || outcome === "disqualified" ? "plain" : outcome}`}>{OUTCOME_LABEL[outcome] ?? outcome}</span></td>
                  <td className="num">{duration(c.duration_s)}</td>
                  <td className="num">{c.llm_calls}</td>
                  <td className="num">${Number(c.cost).toFixed(2)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </>
  )
}
