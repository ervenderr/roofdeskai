import Link from "next/link"
import { connection } from "next/server"
import { redirect } from "next/navigation"
import { getSession, isLive } from "@/lib/data"
import { signIn } from "@/lib/session-actions"

const MESSAGES: Record<string, string> = {
  error: "That key did not work. Check it and try again.",
  down: "Could not reach the API. Try again in a moment.",
  expired: "Your session ended or the key was revoked. Sign in again.",
}

export default async function Login({ searchParams }: { searchParams: Promise<{ error?: string; down?: string; expired?: string }> }) {
  if (!process.env.EXPORT) await connection()
  if (!isLive) {
    return (
      <>
        <h1>Sign in</h1>
        <p className="sub">The static demo has no sign-in. <Link href="/">Back to the demo</Link></p>
      </>
    )
  }
  const q = await searchParams
  if (!q.expired && (await getSession())) redirect("/")
  const msg = q.error ? MESSAGES.error : q.down ? MESSAGES.down : q.expired ? MESSAGES.expired : null
  return (
    <>
      <h1>Sign in</h1>
      <p className="sub">Paste your business API key, or the operator key.</p>
      {msg && <p role="alert">{msg}</p>}
      <form action={signIn} className="card" style={{ maxWidth: 480 }}>
        <label>API key<br />
          <input type="password" name="key" required autoComplete="off" spellCheck={false} style={{ width: "100%", margin: "6px 0 12px" }} />
        </label>
        <button type="submit" className="btn">Sign in</button>
      </form>
    </>
  )
}
