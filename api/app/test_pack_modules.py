import shutil
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import BaseModel, ConfigDict, TypeAdapter, ValidationError

from . import pack as packmod
from .config import settings
from .pack import HHMM, Money, PackError, Percent, load_pack
from .test_pack import MIN_PACK, SLUG, write_pack

FIXTURES = Path(__file__).parent / "tests_data" / "packs"

# NOTE: these pin the byte content of the shipped packs. A deliberate pack edit needs a deliberate pin update here.
# pack_hash walks every file under businesses/<slug>/ except scenarios/, so a stray file (e.g. .DS_Store) changes it.
PINNED = {
    "summit-roofing": "ead72d1bc518723cc15b50065ba26af34f5294ded89622a0c6386eaca3fedded",
    "bright-smile-dental": "8431b23718c15834fd5596c4a7e99dcb8ab634bc098afadc073ce1dbfe71cb13",
}


@pytest.mark.parametrize("slug", PINNED)
def test_shipped_pack_hash_pinned(slug):
    assert load_pack(slug).hash == PINNED[slug]


def test_base_dir_loads_and_default_unchanged(tmp_path, monkeypatch):
    write_pack(tmp_path)
    assert load_pack(SLUG, base=tmp_path).slug == SLUG
    monkeypatch.setattr(settings, "businesses_dir", tmp_path / "nowhere")
    with pytest.raises(PackError):  # default still reads settings.businesses_dir
        load_pack(SLUG)


def test_demo_venue_fixture_loads():
    p = load_pack("demo-venue", base=FIXTURES)
    assert p.meta.timezone == "Europe/Zurich" and p.calendar.slot_hours == (10, 12, 14, 16, 18)


class Thing(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    n: int


@pytest.fixture
def opt(tmp_path, monkeypatch):
    monkeypatch.setattr(packmod, "OPTIONAL_FILES", {"thing": Thing})
    d = write_pack(tmp_path)
    return d


def test_optional_absent_is_none(opt):
    assert packmod._parse_optional(opt / "thing.yaml", Thing) is None
    load_pack(SLUG, base=opt.parent)  # loader tolerates the absent optional file


def test_optional_present_ok(opt):
    (opt / "thing.yaml").write_text("n: 3\n")
    assert packmod._parse_optional(opt / "thing.yaml", Thing).n == 3
    load_pack(SLUG, base=opt.parent)


def test_optional_bad_field_names_file_and_field(opt):
    (opt / "thing.yaml").write_text("n: x\n")
    with pytest.raises(PackError, match=r"thing\.yaml: n:"):
        load_pack(SLUG, base=opt.parent)


def test_optional_empty_file_is_error(opt):
    (opt / "thing.yaml").write_text("")
    with pytest.raises(PackError, match=r"thing\.yaml"):
        load_pack(SLUG, base=opt.parent)


@pytest.mark.parametrize("v,want", [("35.10", Decimal("35.10")), (35, Decimal("35")), ("0", Decimal("0"))])
def test_money_accepts(v, want):
    assert TypeAdapter(Money).validate_python(v) == want


@pytest.mark.parametrize("v", [35.1, True, None, "-1", -1, "1.234", "abc", "NaN"])
def test_money_rejects(v):
    with pytest.raises(ValidationError):
        TypeAdapter(Money).validate_python(v)


def test_percent():
    assert TypeAdapter(Percent).validate_python("10") == Decimal("10")
    for bad in ("0", "100.5", 10.5, None):
        with pytest.raises(ValidationError):
            TypeAdapter(Percent).validate_python(bad)


def test_hhmm():
    assert TypeAdapter(HHMM).validate_python("17:00").hour == 17
    with pytest.raises(ValidationError, match="quote"):
        TypeAdapter(HHMM).validate_python(1020)
    with pytest.raises(ValidationError):
        TypeAdapter(HHMM).validate_python("25:00")


def test_unquoted_time_in_yaml_gives_packerror(opt, monkeypatch):
    class Win(BaseModel):
        model_config = ConfigDict(extra="forbid")
        start: HHMM

    monkeypatch.setattr(packmod, "OPTIONAL_FILES", {"win": Win})
    (opt / "win.yaml").write_text("start: 17:00\n")
    with pytest.raises(PackError, match=r"win\.yaml: start: .*quote"):
        load_pack(SLUG, base=opt.parent)


def test_fixture_copy_independent(tmp_path):
    shutil.copytree(FIXTURES / "demo-venue", tmp_path / "demo-venue")
    assert load_pack("demo-venue", base=tmp_path).hash == load_pack("demo-venue", base=FIXTURES).hash


def test_tenant_fixtures_resolve_packs(venue_tenant, roofing_tenant):
    assert venue_tenant != roofing_tenant
    assert packmod.get_pack(venue_tenant).meta.timezone == "Europe/Zurich"
    assert packmod.get_pack(roofing_tenant).slug == "summit-roofing"
