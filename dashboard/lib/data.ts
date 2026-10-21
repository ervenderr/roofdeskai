import fs from "node:fs"
import path from "node:path"
import type { CallItem, Campaign, ConversationDetail, ConversationRow, Metrics, OutreachMetrics, Prospect, ProspectDetail, QueueItem, ScrapeRun } from "./types"

const API = process.env.API_URL
const KEY = process.env.ADMIN_API_KEY ?? ""

/** Live mode (API_URL set) reads the FastAPI service server-side, so the admin key never reaches the browser.
 *  Otherwise the pages read data/snapshot.json, which is how the static demo is hosted. */
export const isLive = Boolean(API)

type Snapshot = {
  metrics: Metrics; conversations: ConversationRow[]; details: Record<string, ConversationDetail>
  prospects: Prospect[]; prospect_details: Record<string, ProspectDetail>; queue: QueueItem[]; outreach_metrics: OutreachMetrics
  calls: CallItem[]
}

function snapshot(): Snapshot {
  return JSON.parse(fs.readFileSync(path.join(process.cwd(), "data", "snapshot.json"), "utf8"))
}

async function api<T>(route: string): Promise<T> {
  const res = await fetch(`${API}${route}`, { headers: { "X-Admin-Key": KEY }, cache: "no-store" })
  if (!res.ok) throw new Error(`API ${route} returned ${res.status}`)
  return res.json()
}

export const getMetrics = async (): Promise<Metrics> => (isLive ? api("/metrics") : snapshot().metrics)
export const getConversations = async (): Promise<ConversationRow[]> => (isLive ? api("/conversations") : snapshot().conversations)
export const getConversation = async (id: string): Promise<ConversationDetail | null> =>
  isLive ? api<ConversationDetail>(`/conversations/${id}`).catch(() => null) : (snapshot().details[id] ?? null)
export const snapshotIds = (): string[] => Object.keys(snapshot().details)

export const getProspects = async (status?: string): Promise<Prospect[]> =>
  isLive ? api(`/admin/prospects${status ? `?status=${encodeURIComponent(status)}` : ""}`) : snapshot().prospects.filter((p) => !status || p.status === status)
export const getProspect = async (id: string): Promise<ProspectDetail | null> =>
  isLive ? api<ProspectDetail>(`/admin/prospects/${id}`).catch(() => null) : (snapshot().prospect_details[id] ?? null)
export const prospectIds = (): string[] => Object.keys(snapshot().prospect_details ?? {})
export const getQueue = async (): Promise<QueueItem[]> => (isLive ? api("/admin/outreach/queue") : snapshot().queue)
export const getOutreachMetrics = async (): Promise<OutreachMetrics> => (isLive ? api("/admin/outreach/metrics") : snapshot().outreach_metrics)

/** Approve or reject a draft. Server-side only (the admin key never reaches the browser); live mode only. */
export async function reviewDraft(id: number, action: "approve" | "reject"): Promise<void> {
  if (!isLive) throw new Error("the static demo is read-only")
  const res = await fetch(`${API}/admin/outreach/${id}/${action}`, { method: "POST", headers: { "X-Admin-Key": KEY } })
  if (!res.ok) throw new Error(`API ${action} returned ${res.status}`)
}

export const getCampaigns = async (): Promise<Campaign[]> => (isLive ? api("/admin/campaigns") : [])
export const getScrapes = async (): Promise<ScrapeRun[]> => (isLive ? api("/admin/scrapes") : [])

/** Start a Google Maps scrape. Server-side only; returns a message for the form instead of throwing. */
export async function startScrapeRun(input: { campaign_id: number; queries: string[]; depth: number; email: boolean }): Promise<string> {
  if (!isLive) return "The static demo is read-only."
  const res = await fetch(`${API}/admin/scrapes`, {
    method: "POST", headers: { "X-Admin-Key": KEY, "content-type": "application/json" }, body: JSON.stringify(input),
  })
  if (res.ok) return "Scrape started. Results are imported and scored automatically in a few minutes."
  const body = await res.json().catch(() => ({}))
  const detail = typeof body.detail === "string" ? body.detail : "Check the form values."
  return `Could not start the scrape (${res.status}): ${detail}`
}

export const getCalls = async (): Promise<CallItem[]> => (isLive ? api("/admin/call-list") : (snapshot().calls ?? []))

/** Log a phone call outcome. Server-side only; live mode only. */
export async function logCallOutcome(id: number, outcome: string, note: string): Promise<void> {
  if (!isLive) throw new Error("the static demo is read-only")
  const res = await fetch(`${API}/admin/prospects/${id}/call`, {
    method: "POST", headers: { "X-Admin-Key": KEY, "content-type": "application/json" }, body: JSON.stringify({ outcome, note }),
  })
  if (!res.ok) throw new Error(`API call log returned ${res.status}`)
}
