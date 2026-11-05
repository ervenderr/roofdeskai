import { createCipheriv, createDecipheriv, createHash, randomBytes } from "node:crypto"

export type Session = { kind: "tenant" | "operator"; key: string; name: string; modules: string[]; exp: number }

export const SESSION_COOKIE = "rd_session"
export const SESSION_MAX_AGE = 8 * 60 * 60 // seconds

function keyFrom(secret: string): Buffer {
  if (!secret || secret.length < 32) throw new Error("SESSION_SECRET must be at least 32 characters")
  return createHash("sha256").update(secret).digest()
}

export function seal(s: Session, secret: string): string {
  const key = keyFrom(secret)
  const iv = randomBytes(12)
  const c = createCipheriv("aes-256-gcm", key, iv)
  const body = Buffer.concat([c.update(JSON.stringify(s), "utf8"), c.final()])
  return Buffer.concat([iv, c.getAuthTag(), body]).toString("base64url")
}

const isStr = (v: unknown): v is string => typeof v === "string" && v.length > 0

export function unseal(token: string, secret: string): Session | null {
  const key = keyFrom(secret)
  let s: Session
  try {
    const raw = Buffer.from(token, "base64url")
    if (raw.length < 29) return null
    const d = createDecipheriv("aes-256-gcm", key, raw.subarray(0, 12))
    d.setAuthTag(raw.subarray(12, 28))
    s = JSON.parse(Buffer.concat([d.update(raw.subarray(28)), d.final()]).toString("utf8"))
  } catch {
    return null // tampered or foreign cookie means no session
  }
  const ok = s && (s.kind === "tenant" || s.kind === "operator") && isStr(s.key) && isStr(s.name)
    && Array.isArray(s.modules) && s.modules.every((m) => typeof m === "string")
    && typeof s.exp === "number" && s.exp > Date.now() / 1000
  return ok ? s : null
}

export type NavItem = { href: string; label: string; operatorOnly?: boolean; module?: string }

export const NAV: NavItem[] = [
  { href: "/", label: "Overview" },
  { href: "/conversations", label: "Conversations" },
  { href: "/prospects", label: "Prospects", operatorOnly: true },
  { href: "/outreach", label: "Outreach", operatorOnly: true },
  { href: "/calls", label: "Calls", operatorOnly: true },
]

/** Null session (static demo) counts as operator with no modules. */
export function navFor(session: Session | null, items: NavItem[] = NAV): NavItem[] {
  const operator = !session || session.kind === "operator"
  const modules = session?.modules ?? []
  return items.filter((i) => (!i.operatorOnly || operator) && (!i.module || modules.includes(i.module)))
}
