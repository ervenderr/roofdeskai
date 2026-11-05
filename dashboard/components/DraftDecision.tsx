import { canApprove, canReject, decidedMessage, type DraftKind, type DraftStatus } from "@/lib/drafts"
import { decideDraft } from "@/lib/review-actions"

export function DecidedNote({ decided }: { decided: unknown }) {
  const msg = decidedMessage(decided)
  return msg ? <p role="status">{msg}</p> : null
}

export function DraftButtons({ kind, id, status }: { kind: DraftKind; id: number; status: DraftStatus }) {
  const approve = canApprove(status)
  const reject = canReject(status)
  if (!approve && !reject) return null
  return (
    <>
      <div className="row">
        {approve && <form action={decideDraft.bind(null, kind, id, "approve")}><button className="btn primary">Approve</button></form>}
        {reject && <form action={decideDraft.bind(null, kind, id, "reject")}><button className="btn">Reject</button></form>}
      </div>
      <p className="sub">Approving or rejecting only records your decision. Nothing is sent or posted.</p>
    </>
  )
}
