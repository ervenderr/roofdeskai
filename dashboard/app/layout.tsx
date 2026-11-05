import type { Metadata } from "next"
import Link from "next/link"
import { getSession, isLive } from "@/lib/data"
import { signOut } from "@/lib/session-actions"
import { navFor } from "@/lib/session"
import "./globals.css"

export const metadata: Metadata = { title: "RoofDesk AI", description: "AI lead-qualification agent: conversations, outcomes and eval scorecard (synthetic data)." }

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const session = isLive ? await getSession() : null
  return (
    <html lang="en">
      <body>
        <div className="wrap">
          <header className="top">
            <Link href="/" className="brand"><img src="/logo.svg" alt="" width={28} height={28} />RoofDesk AI</Link>
            {(!isLive || session) && <nav>{navFor(session).map((n) => <Link key={n.href} href={n.href}>{n.label}</Link>)}</nav>}
            <span className="badge">{!isLive ? "Static demo · synthetic data" : session ? session.name : "Live API"}</span>
            {session && <form action={signOut}><button type="submit" className="signout">Sign out</button></form>}
          </header>
          {children}
        </div>
      </body>
    </html>
  )
}
