export type EvalMetrics = {
  booking_validity: number; escalation_precision: number; escalation_recall: number; schema_validity: number
  llm_calls: number; latency_p50_s: number; latency_p95_s: number; prompt_tokens: number; completion_tokens: number
  categories: Record<string, { passed: number; total: number }>
}
export type EvalRun = {
  id: number; created_at: string; model: string; prompt_version: string; git_sha: string
  metrics_json: (Partial<EvalMetrics> & { backfilled?: boolean }) | null; total: number; passed: number
}
export type Metrics = {
  conversations: number
  outcomes: Record<string, number>
  escalation_rate: number
  resolved_without_human_rate: number
  funnel: { leads: number; qualified: number; booked: number }
  llm: { calls: number; p50_ms: number | null; p95_ms: number | null; cost: number | string; schema_valid_rate: number | string | null }
  cost_per_conversation: number
  daily: { day: string; conversations: number; escalated: number }[]
  eval_runs: EvalRun[]
}
export type ConversationRow = {
  id: number; lead_id: number; channel: string; state: string; outcome: string | null
  started_at: string; ended_at: string | null; cost: number | string; llm_calls: number; duration_s: number | null
}
export type Message = { role: "user" | "assistant"; content: string; created_at: string }
export type ToolCall = { tool_name: string; args_json: unknown; result_json: unknown; ok: boolean; latency_ms: number; created_at: string }
export type ConversationDetail = { conversation: ConversationRow; messages: Message[]; tool_calls: ToolCall[] }
