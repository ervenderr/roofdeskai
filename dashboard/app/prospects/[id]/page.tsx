import Link from "next/link"
import { notFound } from "next/navigation"
import { connection } from "next/server"
import { getProspect, isLive, prospectIds } from "@/lib/data"
import { STATUS_LABEL, STATUS_TONE, when } from "@/lib/format"

export function generateStaticParams() {
  return isLive ? [] : prospectIds().map((id) => ({ id }))
}

export default async function ProspectPage({ params }: { params: Promise<{ id: string }> }) {
  if (!process.env.EXPORT) await connection()
  const { id } = await params
  const data = await getProspect(id)
  if (!data) notFound()
  const { prospect: p, messages, events } = data
  return (
    <>
      <p className="meta"><Link href="/prospects">← All prospects</Link></p>
      <h1>{p.name}</h1>
      <p className="meta">
        {p.category ?? "business"} · {p.address ?? "no address"} · score <b>{p.score}</b> ·{" "}
        <span className={`pill ${STATUS_TONE[p.status] ?? "plain"}`}>{STATUS_LABEL[p.status] ?? p.status}</span>
      </p>
      <div className="grid2">
        <div className="card">
          <h2>Why this score</h2>
          <ul className="reasons">{p.score_reasons.map((r) => <li key={r}>{r}</li>)}</ul>
        </div>
        <div className="card">
          <h2>Timeline</h2>
          <table><tbody>
            {events.map((e, i) => <tr key={i}><td>{e.kind}</td><td>{e.detail ?? ""}</td><td className="num">{when(e.created_at)}</td></tr>)}
          </tbody></table>
        </div>
      </div>
      <h2>Emails</h2>
      {messages.length === 0 && <p className="sub">Nothing drafted yet.</p>}
      {messages.map((m) => (
        <div key={m.id} className="card draft">
          <div className="head">
            <b>Step {m.step}</b><span className="pill plain">{m.status}</span>
            <span style={{ color: "var(--ink-3)", fontSize: 13 }}>written by {m.source}{m.sent_at ? ` · sent ${when(m.sent_at)}` : ""}</span>
          </div>
          <div><b>{m.subject}</b></div>
          <pre>{m.body}</pre>
        </div>
      ))}
    </>
  )
}
