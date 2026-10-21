import Link from "next/link"
import { connection } from "next/server"
import { getCalls, isLive } from "@/lib/data"
import { logCall } from "@/lib/review-actions"

const OUTCOMES = [["no_answer", "No answer"], ["callback", "Call back"], ["wrong_number", "Wrong number"], ["interested", "Interested"], ["not_interested", "Not interested"], ["do_not_contact", "Do not contact"]]

export default async function Calls() {
  if (!process.env.EXPORT) await connection()
  const rows = await getCalls()
  return (
    <>
      <h1>Calls</h1>
      <p className="sub">Businesses email cannot reach, best first. Talking points come from their public listing only. Log what happened and an interested or not-interested call settles the prospect.</p>
      {rows[0] && (
        <div className="card" style={{ marginBottom: 16 }}>
          <h2>Suggested opener</h2>
          <p style={{ margin: 0 }}>{rows[0].opener}</p>
        </div>
      )}
      {rows.length === 0 && <p className="sub">Nobody to call right now.</p>}
      {rows.map((r) => (
        <div key={r.id} className="card draft">
          <div className="head">
            <b><Link href={`/prospects/${r.id}`}>{r.name}</Link></b>
            <a href={`tel:${r.phone.replace(/\s/g, "")}`}>{r.phone}</a>
            <span style={{ color: "var(--ink-3)", fontSize: 13 }}>{[r.category, r.city].filter(Boolean).join(" · ")} · score {r.score}</span>
            {r.call_outcome && <span className="pill nurture">{r.call_outcome.replace("_", " ")}</span>}
          </div>
          <ul className="reasons">{r.talking_points.map((t) => <li key={t}>{t}</li>)}</ul>
          {isLive && (
            <form action={logCall.bind(null, r.id)} className="row" style={{ marginTop: 12, flexWrap: "wrap" }}>
              <select name="outcome" className="btn">{OUTCOMES.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>
              <input name="note" placeholder="Note (optional)" maxLength={500} className="btn" style={{ flex: 1, minWidth: 160 }} />
              <button className="btn primary">Save</button>
            </form>
          )}
        </div>
      ))}
    </>
  )
}
