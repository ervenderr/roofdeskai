// Swapped in for review-actions.ts in the static export (Server Actions are not supported there).
// The buttons are not rendered in the static demo, so these are never called.
export async function approveDraft(_id: number): Promise<void> {
  throw new Error("the static demo is read-only")
}
export async function rejectDraft(_id: number): Promise<void> {
  throw new Error("the static demo is read-only")
}
export async function startScrape(_prev: string | null, _form: FormData): Promise<string> {
  return "The static demo is read-only."
}
