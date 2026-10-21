import Link from "next/link"
import { connection } from "next/server"
import { getProspects, isLive } from "@/lib/data"
import { STATUS_LABEL, STATUS_TONE } from "@/lib/format"

const FILTERS = ["scored", "drafted", "approved", "sent", "interested", "not_interested", "unsubscribed", "bounced", "no_email"]

export default async function Prospects({ searchParams }: { searchParams: Promise<{ status?: string }> }) {
  if (!process.env.EXPORT) await connection()
  const { status } = isLive ? await searchParams : { status: undefined }
  const rows = await getProspects(status)
  return (
    <>
      <h1>Prospects</h1>
      <p className="sub">Businesses found by the scraper, scored by how likely they are to miss customer enquiries. Fictional businesses for demonstration.</p>
      {isLive && (
        <div className="chips">
          <Link href="/prospects" className={!status ? "on" : ""}>All</Link>
          {FILTERS.map((f) => <Link key={f} href={`/prospects?status=${f}`} className={status === f ? "on" : ""}>{STATUS_LABEL[f]}</Link>)}
        </div>
      )}
      <div className="card" style={{ padding: 0, overflowX: "auto" }}>
        <table>
          <thead><tr><th className="num">Score</th><th>Business</th><th>Category</th><th>Status</th><th className="num">Rating</th><th className="num">Reviews</th><th className="num">Missed-call reviews</th></tr></thead>
          <tbody>
            {rows.map((p) => (
              <tr key={p.id}>
                <td className="num"><b>{p.score}</b></td>
                <td><Link href={`/prospects/${p.id}`}>{p.name}</Link></td>
                <td>{p.category ?? "n/a"}</td>
                <td><span className={`pill ${STATUS_TONE[p.status] ?? "plain"}`}>{STATUS_LABEL[p.status] ?? p.status}</span></td>
                <td className="num">{p.rating ?? "n/a"}</td>
                <td className="num">{p.review_count ?? "n/a"}</td>
                <td className="num">{p.pain_mentions}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </>
  )
}
