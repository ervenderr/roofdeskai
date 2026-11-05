import fs from "node:fs"
import path from "node:path"
import { cookies } from "next/headers"
import { notFound, redirect } from "next/navigation"
import { SESSION_COOKIE, unseal, type Session } from "./session"
import type { CallItem, Campaign, ConversationDetail, ConversationRow, Metrics, OutreachMetrics, Prospect, ProspectDetail, QueueItem, ScrapeRun } from "./types"

const API = process.env.API_URL

/** Live mode (API_URL set) reads the FastAPI service server-side with the signed-in key from the sealed cookie,
 *  so no key reaches the browser. Otherwise the pages read data/snapshot.json, which is how the static demo is hosted. */
export const isLive = Boolean(API)

type Snapshot = {
  metrics: Metrics; conversations: ConversationRow[]; details: Record<string, ConversationDetail>
  prospects: Prospect[]; prospect_details: Record<string, ProspectDetail>; queue: QueueItem[]; outreach_metrics: OutreachMetrics
  calls: CallItem[]
}

function snapshot(): Snapshot {
  return JSON.parse(fs.readFileSync(path.join(process.cwd(), "data", "snapshot.json"), "utf8"))
}

function secret(): string {
  const s = process.env.SESSION_SECRET ?? ""
  if (s.length < 32) throw new Error("SESSION_SECRET must be at least 32 characters")
  return s
}

/** Current session, or null. Never touches cookies in static (non-live) mode. */
export async function getSession(): Promise<Session | null> {
  if (!isLive) return null
  const sec = secret()
  const value = (await cookies()).get(SESSION_COOKIE)?.value
  return value ? unseal(value, sec) : null
}

const authHeaders = (s: Session): Record<string, string> =>
  s.kind === "tenant" ? { "X-API-Key": s.key } : { "X-Admin-Key": s.key }

async function call(route: string, init: RequestInit = {}, opts: { operator?: boolean } = {}): Promise<Response> {
  const s = await getSession()
  if (!s) redirect("/login")
  if (opts.operator && s.kind !== "operator") notFound()
  const res = await fetch(`${API}${route}`, {
    ...init, cache: "no-store", headers: { ...(init.headers as Record<string, string> | undefined), ...authHeaders(s) },
  })
  if (res.status === 401 || res.status === 403) redirect("/login?expired=1")
  return res
}

async function api<T>(route: string, opts: { operator?: boolean; nullOn404?: boolean } = {}): Promise<T> {
  const res = await call(route, {}, opts)
  if (opts.nullOn404 && res.status === 404) return null as T
  if (!res.ok) throw new Error(`API ${route} returned ${res.status}`)
  return res.json()
}

/** Validate a pasted key for sign-in. Does not read cookies; never logs or returns the key. */
export async function checkKey(key: string): Promise<{ kind: "tenant" | "operator"; name: string; modules: string[] } | "bad" | "down"> {
  if (!isLive) return "down"
  const tenant = key.startsWith("rd_live_")
  const route = tenant ? "/tenant/me" : "/admin/tenants"
  try {
    const res = await fetch(`${API}${route}`, { headers: tenant ? { "X-API-Key": key } : { "X-Admin-Key": key }, cache: "no-store" })
    if (res.status === 401 || res.status === 403) return "bad"
    if (res.status !== 200) { console.error(`login check ${route} returned ${res.status}`); return "down" }
    if (!tenant) return { kind: "operator", name: "Operator", modules: [] }
    const body = await res.json()
    if (typeof body?.name !== "string" || !body.name || !Array.isArray(body.enabled_modules) || !body.enabled_modules.every((m: unknown) => typeof m === "string")) {
      console.error("login check: unexpected /tenant/me body")
      return "down"
    }
    return { kind: "tenant", name: body.name, modules: body.enabled_modules }
  } catch (e) {
    console.error(`login check failed: ${e instanceof Error ? e.message : "unknown error"}`)
    return "down"
  }
}

export const getMetrics = async (): Promise<Metrics> => (isLive ? api("/metrics") : snapshot().metrics)
export const getConversations = async (): Promise<ConversationRow[]> => (isLive ? api("/conversations") : snapshot().conversations)
export const getConversation = async (id: string): Promise<ConversationDetail | null> =>
  isLive ? api<ConversationDetail | null>(`/conversations/${id}`, { nullOn404: true }) : (snapshot().details[id] ?? null)
export const snapshotIds = (): string[] => Object.keys(snapshot().details)

export const getProspects = async (status?: string): Promise<Prospect[]> =>
  isLive ? api(`/admin/prospects${status ? `?status=${encodeURIComponent(status)}` : ""}`, { operator: true }) : snapshot().prospects.filter((p) => !status || p.status === status)
export const getProspect = async (id: string): Promise<ProspectDetail | null> =>
  isLive ? api<ProspectDetail | null>(`/admin/prospects/${id}`, { operator: true, nullOn404: true }) : (snapshot().prospect_details[id] ?? null)
export const prospectIds = (): string[] => Object.keys(snapshot().prospect_details ?? {})
export const getQueue = async (): Promise<QueueItem[]> => (isLive ? api("/admin/outreach/queue", { operator: true }) : snapshot().queue)
export const getOutreachMetrics = async (): Promise<OutreachMetrics> => (isLive ? api("/admin/outreach/metrics", { operator: true }) : snapshot().outreach_metrics)

/** Approve or reject a draft. Server-side only (the key never reaches the browser); live mode only. */
export async function reviewDraft(id: number, action: "approve" | "reject"): Promise<void> {
  if (!isLive) throw new Error("the static demo is read-only")
  const res = await call(`/admin/outreach/${id}/${action}`, { method: "POST" }, { operator: true })
  if (!res.ok) throw new Error(`API ${action} returned ${res.status}`)
}

export const getCampaigns = async (): Promise<Campaign[]> => (isLive ? api("/admin/campaigns", { operator: true }) : [])
export const getScrapes = async (): Promise<ScrapeRun[]> => (isLive ? api("/admin/scrapes", { operator: true }) : [])

/** Start a Google Maps scrape. Server-side only; returns a message for the form instead of throwing. */
export async function startScrapeRun(input: { campaign_id: number; queries: string[]; depth: number; email: boolean }): Promise<string> {
  if (!isLive) return "The static demo is read-only."
  const res = await call("/admin/scrapes", {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify(input),
  }, { operator: true })
  if (res.ok) return "Scrape started. Results are imported and scored automatically in a few minutes."
  const body = await res.json().catch(() => ({}))
  const detail = typeof body.detail === "string" ? body.detail : "Check the form values."
  return `Could not start the scrape (${res.status}): ${detail}`
}

export const getCalls = async (): Promise<CallItem[]> => (isLive ? api("/admin/call-list", { operator: true }) : (snapshot().calls ?? []))

/** Log a phone call outcome. Server-side only; live mode only. */
export async function logCallOutcome(id: number, outcome: string, note: string): Promise<void> {
  if (!isLive) throw new Error("the static demo is read-only")
  const res = await call(`/admin/prospects/${id}/call`, {
    method: "POST", headers: { "content-type": "application/json" }, body: JSON.stringify({ outcome, note }),
  }, { operator: true })
  if (!res.ok) throw new Error(`API call log returned ${res.status}`)
}
