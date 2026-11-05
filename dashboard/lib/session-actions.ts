"use server"
import { cookies, headers } from "next/headers"
import { redirect } from "next/navigation"
import { checkKey } from "@/lib/data"
import { SESSION_COOKIE, SESSION_MAX_AGE, seal, type Session } from "@/lib/session"

const MAX_KEY_LEN = 256

export async function signIn(form: FormData): Promise<void> {
  const key = String(form.get("key") ?? "").trim()
  if (!key || key.length > MAX_KEY_LEN) redirect("/login?error=1")
  const r = await checkKey(key)
  if (r === "bad") redirect("/login?error=1")
  if (r === "down") redirect("/login?down=1")
  const session: Session = { kind: r.kind, key, name: r.name, modules: r.modules, exp: Math.floor(Date.now() / 1000) + SESSION_MAX_AGE }
  const host = (await headers()).get("host") ?? ""
  const local = host.startsWith("localhost") || host.startsWith("127.0.0.1")
  ;(await cookies()).set(SESSION_COOKIE, seal(session, process.env.SESSION_SECRET ?? ""), {
    httpOnly: true, sameSite: "lax", secure: !local, path: "/", maxAge: SESSION_MAX_AGE,
  })
  redirect("/")
}

export async function signOut(): Promise<void> {
  ;(await cookies()).delete(SESSION_COOKIE)
  redirect("/login")
}
