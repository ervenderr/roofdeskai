// Pure helpers for the capacity and brief screens. No imports so node can run the check.

type Obj = Record<string, unknown>
const isObj = (v: unknown): v is Obj => typeof v === "object" && v !== null && !Array.isArray(v)
const isStr = (v: unknown): v is string => typeof v === "string"

/** Only the exact string "1" shows all flags; anything else is the open view. */
export const showAll = (v: unknown): boolean => v === "1"

export const flagsRoute = (all: boolean): string => (all ? "/capacity/flags" : "/capacity/flags?open=true")

const FLAG_KIND_LABEL: Record<string, string> = {
  over_capacity: "Over capacity",
  understaffed: "Understaffed",
  under_utilised: "Under-used",
}

export const flagKindLabel = (k: unknown): string => (isStr(k) ? FLAG_KIND_LABEL[k] ?? k : "unknown")

export type FlagState = "open" | "reflagged" | "resolved"

export function flagState(f: { resolved_at: string | null; reflagged_at: string | null }): FlagState {
  if (f.resolved_at) return "resolved"
  return f.reflagged_at ? "reflagged" : "open"
}

export const FLAG_STATE_LABEL: Record<FlagState, string> = { open: "Open", reflagged: "Re-flagged", resolved: "Resolved" }
export const FLAG_STATE_TONE: Record<FlagState, string> = { open: "escalated", reflagged: "escalated", resolved: "booked" }

const DETAIL_FIELDS: [string, string][] = [["staff", "Staff"], ["min_staff", "Min staff"], ["covers", "Covers"], ["capacity", "Capacity"]]

/** Figures come from the API as given; nothing is computed here. */
export function flagDetailParts(details: unknown): string[] {
  if (!isObj(details)) return []
  return DETAIL_FIELDS.flatMap(([k, label]) => {
    const v = details[k]
    return typeof v === "number" || isStr(v) ? [`${label} ${v}`] : []
  })
}

export const sourceStatus = (s: { ok: boolean; error: string | null }): string =>
  s.ok ? "OK" : s.error ? `Unavailable: ${s.error}` : "Unavailable"

export const sourceLabel = (source: unknown): string =>
  source === "mock" ? "mock data" : isStr(source) && source ? source : "unknown source"

export const metricEntries = (m: unknown): [string, string][] =>
  isObj(m) ? Object.entries(m).filter((e): e is [string, string] => isStr(e[1])) : []

export type BriefResponseShape = {
  latest: { local_date: string; text: string; sources: unknown[] } | null
  runs: { run_date: string; created_at: string }[]
}

export function isBriefResponse(v: unknown): v is BriefResponseShape {
  if (!isObj(v) || !Array.isArray(v.runs)) return false
  if (!v.runs.every((r) => isObj(r) && isStr(r.run_date) && isStr(r.created_at))) return false
  if (v.latest === null) return true
  return isObj(v.latest) && isStr(v.latest.text) && isStr(v.latest.local_date) && Array.isArray(v.latest.sources)
}
