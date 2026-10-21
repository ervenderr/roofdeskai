"use server"
import { revalidatePath } from "next/cache"
import { logCallOutcome, reviewDraft, startScrapeRun } from "@/lib/data"

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
