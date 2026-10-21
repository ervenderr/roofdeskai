import type { Metadata } from "next"
import Link from "next/link"
import { isLive } from "@/lib/data"
import "./globals.css"

export const metadata: Metadata = { title: "LeadPilot", description: "AI lead-qualification agent: conversations, outcomes and eval scorecard (synthetic data)." }

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body>
        <div className="wrap">
          <header className="top">
            <Link href="/" className="brand">LeadPilot</Link>
            <nav><Link href="/">Overview</Link><Link href="/conversations">Conversations</Link></nav>
            <span className="badge">{isLive ? "Live API" : "Static demo"} · synthetic data</span>
          </header>
          {children}
        </div>
      </body>
    </html>
  )
}
