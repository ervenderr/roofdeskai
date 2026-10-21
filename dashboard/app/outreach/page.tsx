import Link from "next/link"
import { connection } from "next/server"
import { FunnelChart } from "@/components/Charts"
import { getOutreachMetrics, getQueue, isLive } from "@/lib/data"
import { approveDraft, rejectDraft } from "@/lib/review-actions"

const sum = (m: Record<string, number>, keys: string[]) => keys.reduce((a, k) => a + (m[k] ?? 0), 0)

export default async function Outreach() {
  if (!process.env.EXPORT) await connection()
  const [m, queue] = await Promise.all([getOutreachMetrics(), getQueue()])
  const s = m.prospects
  const found = sum(s, Object.keys(s))
  const contacted = sum(s, ["sent", "replied", "interested", "not_interested", "booked", "unsubscribed", "bounced"])
  const replied = sum(s, ["replied", "interested", "not_interested", "booked"])
  const interested = sum(s, ["interested", "booked"])
  return (
    <>
      <h1>Outreach</h1>
      <p className="sub">Find, draft, send, follow up. Every email below is reviewed by a person before it goes out, unless a campaign has auto-approve turned on.</p>
      <div className="tiles">
        <div className="tile"><div className="label">Emails sent</div><div className="value">{m.messages.sent ?? 0}</div></div>
        <div className="tile"><div className="label">Awaiting your approval</div><div className="value">{m.awaiting_approval}</div></div>
        <div className="tile"><div className="label">Interested</div><div className="value">{interested}</div><div className="note">of {contacted} contacted</div></div>
        <div className="tile"><div className="label">Opted out or bounced</div><div className="value">{m.suppressed}</div><div className="note">never contacted again</div></div>
      </div>
      <div className="card" style={{ marginBottom: 16 }}>
        <h2>Pipeline</h2>
        <FunnelChart stages={[{ name: "Found", value: found }, { name: "Contacted", value: contacted }, { name: "Replied", value: replied }, { name: "Interested", value: interested }, { name: "Booked", value: s.booked ?? 0 }]} />
      </div>
      <h2>Drafts to review</h2>
      {queue.length === 0 && <p className="sub">No drafts waiting.</p>}
      {queue.map((d) => (
        <div key={d.id} className="card draft">
          <div className="head">
            <b><Link href={`/prospects/${d.prospect_id}`}>{d.name}</Link></b>
            <span style={{ color: "var(--ink-3)", fontSize: 13 }}>to {d.email} · step {d.step} · score {d.score} · written by {d.source}</span>
          </div>
          <div><b>{d.subject}</b></div>
          <pre>{d.body}</pre>
          {isLive ? (
            <div className="row">
              <form action={approveDraft.bind(null, d.id)}><button className="btn primary">Approve</button></form>
              <form action={rejectDraft.bind(null, d.id)}><button className="btn">Reject</button></form>
            </div>
          ) : <span style={{ color: "var(--ink-3)", fontSize: 13 }}>Approving is available in the live dashboard.</span>}
        </div>
      ))}
    </>
  )
}
