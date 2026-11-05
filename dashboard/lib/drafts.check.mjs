import assert from "node:assert/strict"
import { canApprove, canReject, decisionOutcome, parseDecision, decidedMessage, DRAFT_PAGE } from "./drafts.ts"

assert.equal(canApprove("pending"), true)
for (const s of ["needs_human", "approved", "rejected", "sent"]) assert.equal(canApprove(s), false)
assert.equal(canReject("pending"), true)
assert.equal(canReject("needs_human"), true)
for (const s of ["approved", "rejected", "sent"]) assert.equal(canReject(s), false)

assert.equal(decisionOutcome(200), "ok")
assert.equal(decisionOutcome(409), "conflict")
assert.equal(decisionOutcome(404), "missing")
assert.equal(decisionOutcome(500), null)
assert.equal(decisionOutcome(422), null)

assert.deepEqual(parseDecision("quote", 7, "approve"), { kind: "quote", id: 7, action: "approve" })
assert.deepEqual(parseDecision("review_reply", 3, "reject"), { kind: "review_reply", id: 3, action: "reject" })
for (const bad of [["x", 1, "approve"], ["quote", 0, "approve"], ["quote", -1, "approve"], ["quote", 1.5, "approve"],
  ["quote", "7", "approve"], ["quote", NaN, "approve"], ["quote", 1, "send"], [], ["quote"], ["quote", 1]]) {
  assert.equal(parseDecision(...bad), null, JSON.stringify(bad))
}

assert.equal(DRAFT_PAGE.quote, "/quotes")
assert.equal(DRAFT_PAGE.review_reply, "/reviews")

for (const k of ["approved", "rejected"]) assert.match(decidedMessage(k), /nothing was sent or posted/i)
for (const k of ["conflict", "missing"]) assert.ok(decidedMessage(k).length > 0)
for (const v of [undefined, "<script>", ["approved"]]) assert.equal(decidedMessage(v), null)

console.log("drafts check ok")
