-- Retention purge (OPS-04): tenant-context DELETE on the PII-bearing engine tables. agent_events stays append-only.
-- FINAL when first applied (apply_migrations has no checksum): any fix goes in 009+.
GRANT DELETE ON drafts, capacity_flags, brief_runs TO app_rw;
