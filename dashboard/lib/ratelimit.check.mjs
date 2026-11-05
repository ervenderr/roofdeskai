import assert from "node:assert/strict"
import { createLimiter } from "./ratelimit.ts"

const L = createLimiter({ max: 3, windowMs: 1000 })
assert.equal(L.blocked("a", 0), false)
L.fail("a", 0); L.fail("a", 100)
assert.equal(L.blocked("a", 200), false)
L.fail("a", 200)
assert.equal(L.blocked("a", 300), true)
assert.equal(L.blocked("b", 300), false) // per key

// sliding: oldest failure ages out
assert.equal(L.blocked("a", 1000), false) // t=0 expired at 1000
L.fail("a", 1000)
assert.equal(L.blocked("a", 1001), true) // 100,200,1000 in window
assert.equal(L.blocked("a", 1100), false) // 100 expired

// clear
L.fail("c", 0); L.fail("c", 0); L.fail("c", 0)
assert.equal(L.blocked("c", 1), true)
L.clear("c")
assert.equal(L.blocked("c", 1), false)

// memory bounded: expired keys are pruned
const M = createLimiter({ max: 3, windowMs: 1000 })
for (let i = 0; i < 500; i++) M.fail("k" + i, 0)
M.fail("fresh", 5000)
assert.ok(M.size() <= 1, "expired entries pruned, got " + M.size())
console.log("ratelimit ok")
