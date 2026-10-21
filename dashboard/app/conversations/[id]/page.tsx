import { connection } from "next/server"
import Link from "next/link"
import { notFound } from "next/navigation"
import { getConversation, isLive, snapshotIds } from "@/lib/data"
import { OUTCOME_LABEL, when } from "@/lib/format"


// Static export needs every id up front; live mode renders on demand.
export function generateStaticParams() {
  return isLive ? [] : snapshotIds().map((id) => ({ id }))
}

export default async function Transcript({ params }: { params: Promise<{ id: string }> }) {
  if (!process.env.EXPORT) await connection() // normal builds render per request; the static export (EXPORT=1) prerenders the snapshot
  const { id } = await params
  const data = await getConversation(id)
  if (!data) notFound()
  const { conversation: c, messages, tool_calls } = data

  // Interleave by time; a tool call belongs after the user message that triggered it.
  const items = [
    ...messages.map((m) => ({ kind: "msg" as const, at: m.created_at, m })),
    ...tool_calls.map((t) => ({ kind: "tool" as const, at: t.created_at, t })),
  ].sort((a, b) => new Date(a.at).getTime() - new Date(b.at).getTime())

  return (
    <>
      <p className="meta"><Link href="/conversations">← All conversations</Link></p>
      <h1>Conversation {c.id}</h1>
      <p className="meta">
        {c.channel} · {when(c.started_at)} · state <b>{c.state}</b> · outcome <b>{OUTCOME_LABEL[c.outcome ?? "open"] ?? c.outcome}</b> · {c.llm_calls} model calls
      </p>
      <div className="thread">
        {items.map((it, i) =>
          it.kind === "msg" ? (
            <div key={i} className={`msg ${it.m.role}`}>{it.m.content}</div>
          ) : (
            <div key={i} className="tool">
              <b>{it.t.tool_name}</b> <span className={it.t.ok ? "ok" : "fail"}>{it.t.ok ? "ok" : "failed"}</span> · {it.t.latency_ms}ms
              <details><summary>details</summary>
                <pre>args: {JSON.stringify(it.t.args_json, null, 1)}{"\n"}result: {JSON.stringify(it.t.result_json, null, 1)}</pre>
              </details>
            </div>
          ),
        )}
      </div>
    </>
  )
}
