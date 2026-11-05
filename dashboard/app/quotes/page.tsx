import { connection } from "next/server"
import { DecidedNote, DraftButtons } from "@/components/DraftDecision"
import { getDrafts, isLive, requireTenantModule } from "@/lib/data"
import { DRAFT_STATUS_LABEL, DRAFT_STATUS_TONE } from "@/lib/drafts"
import { when } from "@/lib/format"
import type { QuotePayload } from "@/lib/types"

export default async function Quotes({ searchParams }: { searchParams: Promise<{ decided?: string }> }) {
  if (!process.env.EXPORT) await connection()
  if (!isLive) {
    return (
      <>
        <h1>Quotes</h1>
        <p className="sub">Quote drafts are not available in the static demo.</p>
      </>
    )
  }
  await requireTenantModule("services")
  const [drafts, q] = await Promise.all([getDrafts("quote"), searchParams])
  return (
    <>
      <h1>Quotes</h1>
      <p className="sub">Drafts are written from customer requests. Nothing goes out from this screen.</p>
      <DecidedNote decided={q.decided} />
      {drafts.length === 0 && <p className="sub">No quote drafts yet.</p>}
      {drafts.map((d) => {
        const p = d.payload as QuotePayload
        const r = p.request
        const parts = r
          ? [r.service_id, r.qty != null ? `qty ${r.qty}` : null, Array.isArray(r.add_on_ids) && r.add_on_ids.length ? `add-ons: ${r.add_on_ids.join(", ")}` : null, r.customer_type].filter(Boolean)
          : []
        const lines = Array.isArray(p.quote?.lines) ? p.quote.lines : []
        return (
          <div key={d.id} className="card draft">
            <div className="head">
              <b>#{d.id}</b>
              <span className={`pill ${DRAFT_STATUS_TONE[d.status] ?? "plain"}`}>{DRAFT_STATUS_LABEL[d.status] ?? d.status}</span>
              <span style={{ color: "var(--ink-3)", fontSize: 13 }}>{when(d.created_at)}</span>
              {p.contact_email && <span>Customer: {p.contact_email}</span>}
            </div>
            {parts.length > 0 && <p>Request: {parts.join(" · ")}</p>}
            {p.needs_human && (
              <>
                <p>Needs a person: {p.needs_human.reason}</p>
                {Array.isArray(p.needs_human.missing) && p.needs_human.missing.length > 0 && <p>Missing: {p.needs_human.missing.join(", ")}</p>}
                {p.customer_email && (<><b>Customer message</b><pre>{p.customer_email}</pre></>)}
              </>
            )}
            {p.quote && (
              <table>
                <thead><tr><th>Item</th><th className="num">Qty</th><th className="num">Unit price</th><th className="num">Amount</th></tr></thead>
                <tbody>
                  {lines.map((l, i) => (
                    <tr key={i}><td>{l.label}</td><td className="num">{l.qty ?? "-"}</td><td className="num">{l.unit_price ?? "-"}</td><td className="num">{l.amount}</td></tr>
                  ))}
                  <tr><td><b>Total</b></td><td /><td /><td className="num"><b>{p.quote.currency} {p.quote.total}</b></td></tr>
                </tbody>
              </table>
            )}
            {p.email_text && <pre>{p.email_text}</pre>}
            {Array.isArray(p.check_failures) && p.check_failures.length > 0 && <p>Email failed checks: {p.check_failures.join(", ")}</p>}
            <DraftButtons kind="quote" id={d.id} status={d.status} />
          </div>
        )
      })}
    </>
  )
}
