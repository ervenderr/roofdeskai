// Sliding-window failure limiter, keyed by client id. Pure: time is passed in.
export function createLimiter({ max, windowMs }: { max: number; windowMs: number }) {
  let hits = new Map<string, number[]>()
  const live = (ts: number[], now: number) => ts.filter((t) => now - t < windowMs)
  const prune = (now: number) => {
    const next = new Map<string, number[]>()
    for (const [id, ts] of hits) {
      const kept = live(ts, now)
      if (kept.length) next.set(id, kept)
    }
    hits = next
  }
  return {
    blocked: (id: string, now: number): boolean => live(hits.get(id) ?? [], now).length >= max,
    fail(id: string, now: number): void {
      prune(now)
      hits.set(id, [...live(hits.get(id) ?? [], now), now])
    },
    clear(id: string): void {
      hits.delete(id)
    },
    size: (): number => hits.size,
  }
}
