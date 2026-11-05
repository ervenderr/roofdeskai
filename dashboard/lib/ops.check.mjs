import assert from "node:assert/strict"
import {
  showAll, flagsRoute, flagKindLabel, flagState, FLAG_STATE_TONE, flagDetailParts,
  sourceStatus, sourceLabel, metricEntries, isBriefResponse,
} from "./ops.ts"

assert.equal(showAll("1"), true)
for (const v of [undefined, "0", "true", ["1"], ""]) assert.equal(showAll(v), false)

assert.equal(flagsRoute(false), "/capacity/flags?open=true")
assert.equal(flagsRoute(true), "/capacity/flags")

assert.equal(flagKindLabel("over_capacity"), "Over capacity")
assert.equal(flagKindLabel("understaffed"), "Understaffed")
assert.equal(flagKindLabel("under_utilised"), "Under-used")
assert.equal(flagKindLabel("weird"), "weird")
assert.equal(flagKindLabel(5), "unknown")

assert.equal(flagState({ resolved_at: "x", reflagged_at: null }), "resolved")
assert.equal(flagState({ resolved_at: null, reflagged_at: "x" }), "reflagged")
assert.equal(flagState({ resolved_at: null, reflagged_at: null }), "open")
assert.equal(FLAG_STATE_TONE.open, "escalated")
assert.equal(FLAG_STATE_TONE.reflagged, "escalated")
assert.equal(FLAG_STATE_TONE.resolved, "booked")

assert.deepEqual(flagDetailParts({ staff: 3, covers: 31, capacity: 30, min_staff: 2 }), ["Staff 3", "Min staff 2", "Covers 31", "Capacity 30"])
assert.deepEqual(flagDetailParts({ capacity: 30, staff: 3 }), ["Staff 3", "Capacity 30"])
assert.deepEqual(flagDetailParts({ staff: {}, covers: [], capacity: true, min_staff: 2 }), ["Min staff 2"])
for (const v of [null, "x", []]) assert.deepEqual(flagDetailParts(v), [])

assert.equal(sourceLabel("mock"), "mock data")
assert.equal(sourceLabel("live"), "live")
assert.equal(sourceLabel(undefined), "unknown source")

assert.deepEqual(metricEntries({ bookings_count: "12", x: 3, y: null }), [["bookings_count", "12"]])
assert.deepEqual(metricEntries(null), [])

assert.equal(sourceStatus({ ok: true, error: null }), "OK")
assert.equal(sourceStatus({ ok: false, error: "TimeoutError" }), "Unavailable: TimeoutError")
assert.equal(sourceStatus({ ok: false, error: null }), "Unavailable")

assert.equal(isBriefResponse({ latest: null, runs: [] }), true)
assert.equal(isBriefResponse({ latest: { local_date: "2026-07-01", text: "t", sources: [] }, runs: [{ run_date: "2026-07-01", created_at: "c" }] }), true)
for (const bad of [null, [], { latest: null }, { latest: "x", runs: [] }, { latest: null, runs: [{}] }, { latest: { text: 1 }, runs: [] }])
  assert.equal(isBriefResponse(bad), false, JSON.stringify(bad))

console.log("ops check ok")
