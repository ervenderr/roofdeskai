"use server"
import { revalidatePath } from "next/cache"
import { reviewDraft } from "@/lib/data"

export async function approveDraft(id: number) {
  await reviewDraft(id, "approve")
  revalidatePath("/outreach")
}

export async function rejectDraft(id: number) {
  await reviewDraft(id, "reject")
  revalidatePath("/outreach")
}
