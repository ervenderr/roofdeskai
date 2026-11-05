export type DraftKind = "quote" | "review_reply"
export type DraftStatus = "pending" | "approved" | "rejected" | "needs_human" | "sent"
export type DraftAction = "approve" | "reject"

export const DRAFT_PAGE: Record<DraftKind, "/quotes" | "/reviews"> = { quote: "/quotes", review_reply: "/reviews" }

export const DRAFT_STATUS_LABEL: Record<DraftStatus, string> = {
  pending: "Waiting for you", approved: "Approved", rejected: "Rejected", needs_human: "Needs a person", sent: "Sent",
}

export const DRAFT_STATUS_TONE: Record<DraftStatus, string> = {
  pending: "nurture", needs_human: "escalated", approved: "booked", sent: "booked", rejected: "plain",
}

// Mirrors _decide from_statuses in api/app/drafts.py; the API stays the authority.
export const canApprove = (status: DraftStatus): boolean => status === "pending"
export const canReject = (status: DraftStatus): boolean => status === "pending" || status === "needs_human"

export function decisionOutcome(httpStatus: number): "ok" | "conflict" | "missing" | null {
  if (httpStatus === 200) return "ok"
  if (httpStatus === 409) return "conflict"
  if (httpStatus === 404) return "missing"
  return null
}

// Bound action args come from the client, so whitelist them before any API call.
export function parseDecision(kind: unknown, id: unknown, action: unknown): { kind: DraftKind; id: number; action: DraftAction } | null {
  if (kind !== "quote" && kind !== "review_reply") return null
  if (action !== "approve" && action !== "reject") return null
  if (typeof id !== "number" || !Number.isSafeInteger(id) || id <= 0) return null
  return { kind, id, action }
}

const DECIDED_MESSAGE: Record<string, string> = {
  approved: "Approved. Nothing was sent or posted; this only records your decision.",
  rejected: "Rejected. Nothing was sent or posted.",
  conflict: "That draft was already decided, so nothing changed.",
  missing: "That draft was not found.",
}

export function decidedMessage(v: unknown): string | null {
  return typeof v === "string" && Object.hasOwn(DECIDED_MESSAGE, v) ? DECIDED_MESSAGE[v] : null
}
