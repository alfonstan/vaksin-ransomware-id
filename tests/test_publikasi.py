"""Aturan publikasi: alamat non-pelaku tidak boleh masuk data publik."""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import update  # noqa: E402


def test_hanya_alamat_dari_pelaku_yang_publik():
    assert update.public_domain({"domain": "contoh.co.id", "domain_via": "judul"}) == "contoh.co.id"
    assert update.public_domain({"domain": "contoh.co.id", "domain_via": "deskripsi"}) == "contoh.co.id"
    for via in ("basis data publik", "mesin pencari", "manual", None):
        assert update.public_domain({"domain": "contoh.co.id", "domain_via": via}) is None


def test_data_publik_tidak_memuat_alamat_temuan():
    out = json.loads((ROOT / "docs/data/ransomware-id.json").read_text())
    assert all(v["domain_src"] == "unggahan" for v in out["victims"] if v["domain"])
    assert all(v["domain_src"] is None for v in out["victims"] if not v["domain"])
    assert not (ROOT / "state" / "site_lookup.json").exists()
    for v in json.loads((ROOT / "state/victims.json").read_text()):
        assert not v.get("domain") or v.get("domain_via") in ("judul", "deskripsi")
