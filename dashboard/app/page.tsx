import { connection } from "next/server"
import { CategoryBars, DailyChart, FunnelChart, TrendChart } from "@/components/Charts"
import { getMetrics } from "@/lib/data"
import type { EvalMetrics } from "@/lib/types"
import { ms, pct } from "@/lib/format"


const CATEGORY_NAME: Record<string, string> = {
  qualified: "Qualified leads", disqualified: "Disqualified leads", vague: "Vague answers", out_of_order: "Out-of-order info",
  faq: "FAQ questions", out_of_knowledge: "Out-of-knowledge", escalation: "Escalation", injection: "Prompt injection", slots: "Slot edge cases",
}

export default async function Overview() {
  if (!process.env.EXPORT) await connection() // normal builds render per request; the static export (EXPORT=1) prerenders the snapshot
  const m = await getMetrics()
  const runs = [...m.eval_runs].reverse()
  const latest = m.eval_runs[0]
  const em = latest?.metrics_json?.categories ? (latest.metrics_json as EvalMetrics) : null
  const daily = [...m.daily].reverse().map((d) => ({ day: d.day.slice(5), handled: d.conversations - d.escalated, escalated: d.escalated }))
  const cats = em ? Object.keys(CATEGORY_NAME).filter((k) => em.categories[k]).map((k) => {
    const v = em.categories[k]
    return { name: CATEGORY_NAME[k], rate: Math.round((100 * v.passed) / v.total), label: `${v.passed}/${v.total}` }
  }) : []

  return (
    <>
      <h1>Overview</h1>
      <p className="sub">Summit Roofing (fictional). Every number below comes from the agent running against synthetic leads.</p>

      <div className="tiles">
        <div className="tile"><div className="label">Conversations</div><div className="value">{m.conversations}</div></div>
        <div className="tile"><div className="label">Resolved without a human</div><div className="value">{pct(m.resolved_without_human_rate)}</div>
          <div className="note">Escalation rate {pct(m.escalation_rate)}</div></div>
        <div className="tile"><div className="label">LLM latency p50 / p95</div><div className="value">{ms(m.llm.p50_ms)} / {ms(m.llm.p95_ms)}</div>
          <div className="note">{m.llm.calls} model calls</div></div>
        <div className="tile"><div className="label">Cost per conversation</div><div className="value">${m.cost_per_conversation.toFixed(2)}</div>
          <div className="note">Local open-weight model</div></div>
      </div>

      <div className="grid2">
        <div className="card"><h2>Conversations per day</h2><DailyChart data={daily} /></div>
        <div className="card"><h2>Funnel: leads to booked</h2>
          <FunnelChart stages={[{ name: "Leads", value: m.funnel.leads }, { name: "Qualified", value: m.funnel.qualified }, { name: "Booked", value: m.funnel.booked }]} /></div>
      </div>

      <h1 style={{ marginTop: 32 }}>Eval scorecard</h1>
      {latest ? (
        <p className="sub">
          {latest.passed}/{latest.total} scenarios passed · model <code>{latest.model}</code> · prompt <code>{latest.prompt_version}</code> · commit <code>{latest.git_sha}</code>
        </p>
      ) : <p className="sub">No eval runs yet. Run <code>make eval</code>.</p>}

      {em && (
        <div className="tiles">
          <div className="tile"><div className="label">Booking validity</div><div className="value">{pct(em.booking_validity)}</div><div className="note">must be 100%</div></div>
          <div className="tile"><div className="label">Escalation precision / recall</div><div className="value">{pct(em.escalation_precision)} / {pct(em.escalation_recall)}</div></div>
          <div className="tile"><div className="label">Schema validity (first try)</div><div className="value">{pct(em.schema_validity)}</div><div className="note">{em.llm_calls} model calls</div></div>
          <div className="tile"><div className="label">Turn latency p50 / p95</div><div className="value">{em.latency_p50_s.toFixed(1)}s / {em.latency_p95_s.toFixed(1)}s</div></div>
        </div>
      )}

      <div className="grid2">
        {cats.length > 0 && <div className="card"><h2>Pass rate by category (latest run)</h2><CategoryBars data={cats} /></div>}
        {runs.length > 0 && <div className="card"><h2>Trend across eval runs</h2>
          <TrendChart data={runs.map((r, i) => ({
            run: `Run ${i + 1}`, rate: Math.round((100 * r.passed) / Math.max(r.total, 1)),
            detail: `${r.prompt_version} · ${r.passed}/${r.total}${r.metrics_json?.backfilled ? " (from saved report)" : ""}`,
          }))} /></div>}
      </div>
    </>
  )
}
