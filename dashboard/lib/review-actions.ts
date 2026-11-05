"use server"
import { revalidatePath } from "next/cache"
import { redirect } from "next/navigation"
import { decideTenantDraft, logCallOutcome, reviewDraft, startScrapeRun } from "@/lib/data"
import { DRAFT_PAGE, parseDecision } from "@/lib/drafts"

export async function approveDraft(id: number) {
  await reviewDraft(id, "approve")
  revalidatePath("/outreach")
}

export async function rejectDraft(id: number) {
  await reviewDraft(id, "reject")
  revalidatePath("/outreach")
}

export async function startScrape(_prev: string | null, form: FormData): Promise<string> {
  const message = await startScrapeRun({
    campaign_id: Number(form.get("campaign_id")), queries: [String(form.get("query") ?? "").trim()],
    depth: Number(form.get("depth") ?? 1), email: form.get("email") === "on",
  })
  revalidatePath("/outreach")
  return message
}

export async function logCall(id: number, form: FormData) {
  await logCallOutcome(id, String(form.get("outcome")), String(form.get("note") ?? ""))
  revalidatePath("/calls")
}

/** Approve or reject a tenant draft. Only records the decision; nothing is sent or posted. */
export async function decideDraft(kind: unknown, id: unknown, action: unknown): Promise<void> {
  const d = parseDecision(kind, id, action)
  if (!d) throw new Error("invalid draft decision")
  const result = await decideTenantDraft(d.id, d.action)
  revalidatePath(DRAFT_PAGE[d.kind])
  const decided = result === "ok" ? (d.action === "approve" ? "approved" : "rejected") : result
  redirect(`${DRAFT_PAGE[d.kind]}?decided=${decided}`)
}
