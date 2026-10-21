"use client"
import { useActionState } from "react"
import { startScrape } from "@/lib/review-actions"
import type { Campaign } from "@/lib/types"

export function FindProspects({ campaigns }: { campaigns: Campaign[] }) {
  const [message, action, pending] = useActionState(startScrape, null)
  const real = campaigns.filter((c) => !c.public_demo)
  const options = real.length ? real : campaigns
  return (
    <form action={action} className="card" style={{ marginBottom: 16 }}>
      <h2>Find prospects (Google Maps)</h2>
      {options.length === 0 ? <p className="sub">Create a campaign first (POST /admin/campaigns).</p> : (
        <div style={{ display: "grid", gap: 10, gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", alignItems: "end" }}>
          <label>Campaign<br /><select name="campaign_id" className="btn" style={{ width: "100%" }}>{options.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
          <label>Search<br /><input name="query" required minLength={3} maxLength={120} placeholder="dentist in Davao City" className="btn" style={{ width: "100%" }} /></label>
          <label>Depth<br /><select name="depth" className="btn" style={{ width: "100%" }}><option value="1">1 (about 20 results)</option><option value="2">2</option><option value="3">3</option></select></label>
          <label style={{ fontSize: 13 }}><input type="checkbox" name="email" /> Also look for emails (slower)</label>
          <button className="btn primary" disabled={pending}>{pending ? "Starting…" : "Start scrape"}</button>
        </div>
      )}
      {message && <p className="sub" style={{ margin: "12px 0 0" }}>{message}</p>}
    </form>
  )
}
