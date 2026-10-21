import fs from "node:fs"
import path from "node:path"
import type { ConversationDetail, ConversationRow, Metrics } from "./types"

const API = process.env.API_URL
const KEY = process.env.ADMIN_API_KEY ?? ""

/** Live mode (API_URL set) reads the FastAPI service server-side, so the admin key never reaches the browser.
 *  Otherwise the pages read data/snapshot.json, which is how the static demo is hosted. */
export const isLive = Boolean(API)

type Snapshot = { metrics: Metrics; conversations: ConversationRow[]; details: Record<string, ConversationDetail> }

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
