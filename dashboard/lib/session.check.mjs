import assert from "node:assert/strict"
import { seal, unseal, navFor, NAV } from "./session.ts"

const SECRET = "test-secret-test-secret-test-secret-1234"
const now = () => Math.floor(Date.now() / 1000)
const tenant = { kind: "tenant", key: "rd_live_abc", name: "Acme Dental", modules: ["capacity"], exp: now() + 600 }
const operator = { kind: "operator", key: "adm", name: "Operator", modules: [], exp: now() + 600 }

// round trip
assert.deepEqual(unseal(seal(tenant, SECRET), SECRET), tenant)
// wrong secret
assert.equal(unseal(seal(tenant, SECRET), SECRET + "x"), null)
// tampered: flip one char
const tok = seal(tenant, SECRET)
const i = Math.floor(tok.length / 2)
const flipped = tok.slice(0, i) + (tok[i] === "A" ? "B" : "A") + tok.slice(i + 1)
assert.equal(unseal(flipped, SECRET), null)
// expired
assert.equal(unseal(seal({ ...tenant, exp: now() - 1 }, SECRET), SECRET), null)
// malformed
assert.equal(unseal("", SECRET), null)
assert.equal(unseal("garbage", SECRET), null)
const { kind, ...noKind } = tenant
assert.equal(unseal(seal(noKind, SECRET), SECRET), null)
assert.equal(unseal(seal({ ...tenant, kind: "root" }, SECRET), SECRET), null)
// short secret throws
assert.throws(() => seal(tenant, "short"))
assert.throws(() => unseal(tok, "short"))

// nav
assert.equal(navFor(null).length, 5)
assert.deepEqual(navFor(tenant).map((n) => n.href), ["/", "/conversations"])
assert.equal(navFor(operator).length, 5)
const items = [...NAV, { href: "/x", label: "X", module: "capacity" }, { href: "/y", label: "Y", module: "reviews" }]
const hrefs = navFor(tenant, items).map((n) => n.href)
assert.ok(hrefs.includes("/x") && !hrefs.includes("/y"))

const dental = { ...tenant, modules: ["services", "reviews"] }
assert.ok(["/quotes", "/reviews"].every((h) => navFor(dental).map((n) => n.href).includes(h)))
for (const s of [tenant, operator, null]) {
  const h = navFor(s).map((n) => n.href)
  assert.ok(!h.includes("/quotes") && !h.includes("/reviews"))
}

console.log("session check ok")
