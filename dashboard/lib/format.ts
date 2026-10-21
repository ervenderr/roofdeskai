export const pct = (x: number | null | undefined, digits = 0) => (x == null ? "n/a" : `${(100 * x).toFixed(digits)}%`)
export const ms = (x: number | null | undefined) => (x == null ? "n/a" : x >= 1000 ? `${(x / 1000).toFixed(1)}s` : `${Math.round(x)}ms`)
export const when = (iso: string) => new Date(iso).toLocaleString("en-GB", { dateStyle: "medium", timeStyle: "short", timeZone: "UTC" }) + " UTC"
export const duration = (s: number | null) => (s == null ? "n/a" : s < 90 ? `${Math.round(s)}s` : `${Math.round(s / 60)}m`)
export const OUTCOME_LABEL: Record<string, string> = { booked: "Booked", disqualified: "Disqualified", escalated: "Escalated", nurture: "Nurture", open: "Open" }
export const STATUS_LABEL: Record<string, string> = {
  scored: "Ready to draft", no_email: "No email", drafted: "Draft to review", approved: "Approved", sent: "Contacted",
  replied: "Replied", interested: "Interested", not_interested: "Not interested", booked: "Booked", unsubscribed: "Unsubscribed",
  bounced: "Bounced", skipped: "Skipped",
}
export const STATUS_TONE: Record<string, string> = { interested: "booked", booked: "booked", unsubscribed: "escalated", bounced: "escalated", drafted: "nurture", approved: "nurture" }
