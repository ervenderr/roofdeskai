"""scripts/gen_docs.py: deterministic SOPs, runbooks, README blocks and the drift check."""
import re
import shutil
from pathlib import Path

import pytest

from scripts import gen_docs

ROOT = gen_docs.ROOT
PACKS = sorted(p.name for p in (ROOT / "businesses").iterdir() if (p / "pack.yaml").exists())
WORKFLOWS = sorted(p.stem for p in (ROOT / "n8n" / "workflows").glob("*.json"))
SENTINELS = {"RETENTION_DAYS": "sentinel-retention-77", "PUBLIC_DEMO_TENANT_ID": "sentinel-tenant-88",
             "APP_DATABASE_URL": "sentinel-dburl-99", "TENANT_API_KEYS": "sentinel-keys-11",
             "OWNER_EMAIL": "sentinel-owner-22"}


@pytest.fixture(scope="module")
def docs():
    return gen_docs.render_all()


def test_render_all_is_stable_and_sorted(docs):
    again = gen_docs.render_all()
    assert docs == again
    assert list(docs) == sorted(docs)


def test_key_set(docs):
    want = {f"docs/generated/{p}/sop-{w}.md" for p in PACKS for w in WORKFLOWS}
    want |= {f"docs/generated/{p}/runbook.md" for p in PACKS}
    assert set(docs) == want


def test_hygiene(docs):
    for path, body in docs.items():
        assert body.endswith("\n") and not body.endswith("\n\n"), path
        assert "\r" not in body, path
        assert "/Users/" not in body, path
        assert not re.search(r"\b[0-9a-f]{40}\b", body), path
        assert not re.search(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}", body), path
        assert "rd_live_" not in body and "sk-" not in body, path
    for slug in PACKS:
        from app.pack import load_pack
        h = load_pack(slug).hash
        assert not any(h in b for b in docs.values())


def test_sop_content(docs):
    from app.pack import load_pack
    p = load_pack("summit-roofing")
    sop = docs["docs/generated/summit-roofing/sop-inbound-message.md"]
    assert p.meta.business in sop and p.meta.timezone in sop
    assert "webhook" in sop and "inbound-message" in sop
    assert "16" in sop and "tenant key" in sop
    for c in p.escalation.always_human:
        assert c in sop
    assert p.messages.owner_alert_subject in sop
    assert "admin key" in docs["docs/generated/summit-roofing/sop-followup-scheduler.md"]


def test_runbook_content(docs):
    rb = docs["docs/generated/bright-smile-dental/runbook.md"]
    for needle in ("PUBLIC_DEMO_TENANT_ID", "APP_DATABASE_URL", "TENANT_API_KEYS", "OWNER_EMAIL", "RETENTION_DAYS",
                   "docs/data-map.md", "make new-business", "make gen-docs", "make check-shared", "144"):
        assert needle in rb, needle


def test_new_pack_gets_docs(tmp_path):
    src = ROOT / "api" / "app" / "tests_data" / "packs" / "demo-venue"
    dst = tmp_path / "biz" / "fake-pack"
    shutil.copytree(src, dst)
    meta = (dst / "pack.yaml").read_text().replace("demo-venue", "fake-pack")
    (dst / "pack.yaml").write_text(meta)
    out = gen_docs.render_all(businesses_dir=tmp_path / "biz")
    assert "docs/generated/fake-pack/runbook.md" in out
    assert f"docs/generated/fake-pack/sop-{WORKFLOWS[0]}.md" in out
    assert not any("summit-roofing" in k for k in out)


def test_cwd_and_env_invariance(docs, monkeypatch, tmp_path):
    for k, v in SENTINELS.items():
        monkeypatch.setenv(k, v)
    monkeypatch.chdir(tmp_path)
    out = gen_docs.render_all()
    assert out == docs
    assert not any(s in b for b in out.values() for s in SENTINELS.values())


def test_missing_placeholder_raises():
    with pytest.raises(KeyError):
        gen_docs.fill("hello $name $missing", name="x")


def test_main_writes_and_removes_stale(tmp_path, docs):
    stale = tmp_path / "docs" / "generated" / "summit-roofing" / "old.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("x\n")
    gen_docs.write_docs(docs, tmp_path)
    assert not stale.exists()
    for rel, body in docs.items():
        assert (tmp_path / rel).read_text() == body


def test_drift_generated_docs(docs):
    gen = ROOT / "docs" / "generated"
    on_disk = {p.relative_to(ROOT).as_posix() for p in gen.rglob("*") if p.is_file()}
    assert on_disk == set(docs), "run make gen-docs"
    for rel, body in docs.items():
        assert (ROOT / rel).read_text() == body, f"{rel} drifted: run make gen-docs"


# README generated blocks
SC = ("<!-- BEGIN GENERATED: scorecard -->", "<!-- END GENERATED: scorecard -->")
CAT = ("<!-- BEGIN GENERATED: catalog -->", "<!-- END GENERATED: catalog -->")
SKELETON = f"head\n{SC[0]}\nold\n{SC[1]}\nmid\n{CAT[0]}\nold\n{CAT[1]}\ntail\n"


def test_render_readme_replaces_only_between_markers_and_is_idempotent():
    once = gen_docs.render_readme(SKELETON)
    assert once.startswith(f"head\n{SC[0]}\n") and f"{SC[1]}\nmid\n{CAT[0]}\n" in once
    assert "old" not in once and once.endswith(f"{CAT[1]}\ntail\n")
    assert gen_docs.render_readme(once) == once


@pytest.mark.parametrize("marker", [SC[0], SC[1], CAT[0], CAT[1]])
def test_render_readme_missing_marker_raises(marker):
    with pytest.raises(ValueError, match="marker"):
        gen_docs.render_readme(SKELETON.replace(marker, ""))


def test_scorecard_rows():
    block = gen_docs.scorecard_block()
    row = {l.split("|")[1].strip(): l for l in block.splitlines() if l.startswith("| ") and "/" in l}
    assert "94/96" in row["summit-roofing"]
    assert "43/43" in row["bright-smile-dental"]
    assert "quote" in block and "cases" in block


def test_scorecard_missing_baseline_raises(tmp_path):
    src = ROOT / "api" / "app" / "tests_data" / "packs" / "demo-venue"
    shutil.copytree(src, tmp_path / "fake-pack")
    (tmp_path / "fake-pack" / "pack.yaml").write_text((src / "pack.yaml").read_text().replace("demo-venue", "fake-pack"))
    with pytest.raises(FileNotFoundError):
        gen_docs.scorecard_block(tmp_path)


def test_catalog_rows():
    block = gen_docs.catalog_block()
    assert [l.split("|")[1].strip() for l in block.splitlines()[2:]] == sorted(
        l.split("|")[1].strip() for l in block.splitlines()[2:])
    assert len(block.splitlines()) == 2 + len(WORKFLOWS)
    assert "Lead flow" in block and "| no |" in block and "| yes |" in block


def test_inputs_ignore_reports():
    src = Path(gen_docs.__file__).read_text()
    body = src.split("def scorecard_block")[1].split("def catalog_block")[0]
    assert "reports" not in body and "glob(" not in body and "default_baseline_path" in body


def test_drift_readme():
    text = (ROOT / "README.md").read_text()
    assert gen_docs.render_readme(text) == text, "run make gen-docs"
    assert "Catalog: 3 tenant-aware workflows" not in text
    assert "Latest run: **94/96 scenarios**" in text
