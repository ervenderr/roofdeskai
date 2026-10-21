"use client"
import { Bar, BarChart, CartesianGrid, Cell, LabelList, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts"

const AXIS = { stroke: "var(--grid)" }
const tick = { fill: "var(--ink-2)", fontSize: 12 }

function Tip({ active, payload, label, unit = "" }: { active?: boolean; payload?: { name: string; value: number; color?: string }[]; label?: string; unit?: string }) {
  if (!active || !payload?.length) return null
  return (
    <div className="rt">
      <div style={{ color: "var(--ink-2)", marginBottom: 2 }}>{label}</div>
      {payload.map((p) => <div key={p.name}>{p.name}: <b>{p.value}{unit}</b></div>)}
    </div>
  )
}

function Table({ head, rows }: { head: string[]; rows: (string | number)[][] }) {
  return (
    <details className="table"><summary>View as table</summary>
      <table><thead><tr>{head.map((h) => <th key={h}>{h}</th>)}</tr></thead>
        <tbody>{rows.map((r, i) => <tr key={i}>{r.map((c, j) => <td key={j}>{c}</td>)}</tr>)}</tbody></table>
    </details>
  )
}

export function DailyChart({ data }: { data: { day: string; handled: number; escalated: number }[] }) {
  return (
    <>
      <div className="chart">
        <ResponsiveContainer>
          <BarChart data={data} margin={{ top: 8, right: 8, bottom: 0, left: -20 }} barCategoryGap="30%">
            <CartesianGrid vertical={false} stroke="var(--grid)" />
            <XAxis dataKey="day" tick={tick} axisLine={AXIS} tickLine={false} />
            <YAxis allowDecimals={false} tick={tick} axisLine={false} tickLine={false} />
            <Tooltip content={<Tip />} cursor={{ fill: "var(--chip)" }} />
            <Legend iconType="square" iconSize={10} formatter={(v: string) => <span style={{ color: "var(--ink-2)", fontSize: 13 }}>{v}</span>} />
            <Bar isAnimationActive={false} dataKey="handled" name="Handled by agent" stackId="a" fill="var(--series-1)" stroke="var(--card)" strokeWidth={2} />
            <Bar isAnimationActive={false} dataKey="escalated" name="Escalated to human" stackId="a" fill="var(--series-2)" stroke="var(--card)" strokeWidth={2} radius={[4, 4, 0, 0]} />
          </BarChart>
        </ResponsiveContainer>
      </div>
      <Table head={["Day", "Handled", "Escalated"]} rows={data.map((d) => [d.day, d.handled, d.escalated])} />
    </>
  )
}

export function FunnelChart({ stages }: { stages: { name: string; value: number }[] }) {
  return (
    <>
      <div className="chart" style={{ height: 160 }}>
        <ResponsiveContainer>
          <BarChart data={stages} layout="vertical" margin={{ top: 4, right: 32, bottom: 0, left: 0 }} barCategoryGap="25%">
            <XAxis type="number" hide domain={[0, "dataMax"]} />
            <YAxis type="category" dataKey="name" width={80} tick={tick} axisLine={false} tickLine={false} />
            <Tooltip content={<Tip />} cursor={{ fill: "var(--chip)" }} />
            <Bar isAnimationActive={false} dataKey="value" name="Leads" radius={[0, 4, 4, 0]} label={{ position: "right", fill: "var(--ink)", fontSize: 13 }}>
              {stages.map((_, i) => <Cell key={i} fill={`var(--ord-${i + 1})`} />)}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <Table head={["Stage", "Leads"]} rows={stages.map((s) => [s.name, s.value])} />
    </>
  )
}

export function TrendChart({ data }: { data: { run: string; rate: number; detail: string }[] }) {
  return (
    <>
      <div className="chart">
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 12, right: 12, bottom: 0, left: -12 }}>
            <CartesianGrid vertical={false} stroke="var(--grid)" />
            <XAxis dataKey="run" tick={tick} axisLine={AXIS} tickLine={false} />
            <YAxis domain={[0, 100]} unit="%" tick={tick} axisLine={false} tickLine={false} />
            <Tooltip content={<Tip unit="%" />} />
            <Line isAnimationActive={false} dataKey="rate" name="Scenarios passed" stroke="var(--series-1)" strokeWidth={2} dot={{ r: 4, fill: "var(--series-1)", stroke: "var(--card)", strokeWidth: 2 }} />
          </LineChart>
        </ResponsiveContainer>
      </div>
      <Table head={["Run", "Prompt · passed", "Passed %"]} rows={data.map((d) => [d.run, d.detail, d.rate])} />
    </>
  )
}

export function CategoryBars({ data }: { data: { name: string; rate: number; label: string }[] }) {
  return (
    <>
      <div className="chart" style={{ height: 270 }}>
        <ResponsiveContainer>
          <BarChart data={data} layout="vertical" margin={{ top: 4, right: 48, bottom: 0, left: 0 }} barCategoryGap="22%">
            <XAxis type="number" hide domain={[0, 100]} />
            <YAxis type="category" dataKey="name" width={118} tick={tick} axisLine={false} tickLine={false} />
            <Tooltip content={<Tip unit="%" />} cursor={{ fill: "var(--chip)" }} />
            <Bar isAnimationActive={false} dataKey="rate" name="Passed" fill="var(--series-1)" radius={[0, 4, 4, 0]}>
              <LabelList dataKey="label" position="right" fill="var(--ink)" fontSize={12} />
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      <Table head={["Category", "Passed"]} rows={data.map((d) => [d.name, d.label])} />
    </>
  )
}
