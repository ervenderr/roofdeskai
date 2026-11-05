// Swapped in for session-actions.ts in the static export (Server Actions are not supported there).
// The login form and sign-out button are not rendered in the static demo, so these are never called.
export async function signIn(_form: FormData): Promise<void> {
  throw new Error("the static demo has no sign-in")
}
export async function signOut(): Promise<void> {
  throw new Error("the static demo has no sign-in")
}
