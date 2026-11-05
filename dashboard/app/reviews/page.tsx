import { connection } from "next/server"
import { DecidedNote, DraftButtons } from "@/components/DraftDecision"
import { getDrafts, isLive, requireTenantModule } from "@/lib/data"
import { DRAFT_STATUS_LABEL, DRAFT_STATUS_TONE } from "@/lib/drafts"
import { when } from "@/lib/format"
import type { ReviewPayload } from "@/lib/types"

export default async function Reviews({ searchParams }: { searchParams: Promise<{ decided?: string }> }) {
  if (!process.env.EXPORT) await connection()
  if (!isLive) {
    return (
      <>
        <h1>Reviews</h1>
        <p className="sub">Review replies are not available in the static demo.</p>
      </>
    )
  }
  await requireTenantModule("reviews")
  const [drafts, q] = await Promise.all([getDrafts("review_reply"), searchParams])
  return (
    <>
      <h1>Reviews</h1>
      <p className="sub">Reply drafts for customer reviews. Nothing is posted from this screen.</p>
      <DecidedNote decided={q.decided} />
      {drafts.length === 0 && <p className="sub">No review reply drafts yet.</p>}
      {drafts.map((d) => {
        const p = d.payload as ReviewPayload
        return (
          <div key={d.id} className="card draft">
            <div className="head">
              <b>#{d.id}</b>
              <span className={`pill ${DRAFT_STATUS_TONE[d.status] ?? "plain"}`}>{DRAFT_STATUS_LABEL[d.status] ?? d.status}</span>
              {p.platform && <span>{p.platform}</span>}
              {p.rating != null && <span>{p.rating}/5</span>}
              <span style={{ color: "var(--ink-3)", fontSize: 13 }}>{when(d.created_at)}</span>
            </div>
            {p.review_text && (<><b>Review</b><pre>{p.review_text}</pre></>)}
            {p.reply_text ? (
              <><b>Draft reply</b><pre>{p.reply_text}</pre></>
            ) : Array.isArray(p.violations) && p.violations.length > 0 ? (
              <p>Blocked after {p.attempts ?? "several"} attempts: {p.violations.join(", ")}</p>
            ) : null}
            <DraftButtons kind="review_reply" id={d.id} status={d.status} />
          </div>
        )
      })}
    </>
  )
}
