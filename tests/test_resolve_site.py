"""Uji pencocokan situs resmi (respons basis data publik ditiru, tanpa jaringan)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import resolve_site as rs  # noqa: E402

ENT = {
    "Q1": ("PT Sarimelati Kencana Tbk.", "Q252", "http://www.sarimelatikencana.co.id/"),
    "Q2": ("Dinas Komunikasi Dan Informatika Kabupaten Merauke", "Q252", "http://www.merauke.go.id/"),
    "Q3": ("Pelabuhan Indonesia II", "Q252", "https://www.indonesiaport.co.id/"),
    "Q4": ("Solaria", "Q252", "https://solariaresto.co.id/"),
    "Q5": ("Solaria", "Q29", "https://solaria.es/"),            # Spanyol, bukan Indonesia
    "Q6": ("Garuda Indonesia", "Q252", "https://www.garuda-indonesia.com/"),
    "Q7": ("Kecamatan Samudera", "Q252", "https://kecsamudera.sigapaceh.id/"),
    "Q8": ("Pertamina", "Q252", "http://www.pertamina.com"),
}
DESC = {"Q7": "kecamatan di Kabupaten Aceh Utara, Aceh"}
SEARCH = {"sarimelati kencana": ["Q1"], "bintan bank": [], "ilcs pelindo": ["Q3"], "solaria": ["Q5", "Q4"],
          "garuda airlines airports indonesia": ["Q6"],
          "samudera": ["Q7"], "pertamina": ["Q8"]}


def fake_get(url, headers=None, timeout=30):
    if "wbsearchentities" in url:
        q = url.split("search=")[1].replace("+", " ")
        return json.dumps({"search": [{"id": i} for i in SEARCH.get(q, [])]}).encode()
    ids = url.split("ids=")[1].split("%7C")
    ents = {i: {"labels": {"id": {"value": ENT[i][0]}}, "aliases": {},
                "descriptions": {"id": {"value": DESC.get(i, "perusahaan Indonesia")}},
                "claims": {"P17": [{"mainsnak": {"datavalue": {"value": {"id": ENT[i][1]}}}}],
                           "P856": [{"mainsnak": {"datavalue": {"value": ENT[i][2]}}}]}} for i in ids}
    return json.dumps({"entities": ents}).encode()


def run(name):
    rs._get, rs.alive = fake_get, (lambda h: True)
    return rs.resolve(name)


def test_nama_khas_ketemu():
    assert run("Sarimelati Kencana Tbk PT") == ("sarimelatikencana.co.id", "basis data publik")
    assert run("Solaria")[0] == "solariaresto.co.id"            # entitas luar negeri dibuang


def test_nama_generik_tidak_dicari():
    assert rs.query_name("Dinas Komunikasi dan Informatika") is None
    assert run("Dinas Komunikasi dan Informatika")[0] is None    # bukan merauke.go.id


def test_anak_usaha_tidak_disamakan_induk():
    assert run("ILCS Pelindo (port logistics operations)")[0] is None


def test_judul_dengan_noise():
    assert run("Garuda Indonesia Airlines, Airports")[0] == "garuda-indonesia.com"
    assert rs.query_name("PT. Bank Perekonomian Rakyat Bintan NEW") == "bank perekonomian rakyat bintan"


def test_nama_satu_kata_tidak_nyasar_ke_wilayah():
    # kasus nyata: "Samudera" (pelayaran) sempat dicocokkan ke situs Kecamatan Samudera, Aceh
    assert run("Samudera (coastal shipping operations)")[0] is None
    assert run("Pertamina")[0] == "pertamina.com"            # satu kata, label persis sama: boleh
