"""Mencari situs resmi organisasi korban bila unggahan pelaku tidak menyebut situsnya.

Urutan sumber (berhenti di yang pertama lolos validasi):
  1. Basis data publik terstruktur (Wikidata, properti "official website" P856), gratis.
  2. Mesin pencari (Brave Search API), hanya bila secret BRAVE_API_KEY diisi.

Prinsip: lebih baik KOSONG daripada SALAH. Situs yang salah membuat organisasi lain
tampak sebagai korban dan, bila dinilai Site Intel, mendapat penilaian yang bukan miliknya.
Karena itu:
  - Nama generik tanpa wilayah/identitas khas (mis. "Dinas Komunikasi dan Informatika",
    "Pemerintah Kabupaten", "Rumah Sakit") TIDAK dicari: hasilnya hampir pasti salah sasaran.
  - Hasil hanya diterima bila semua kata khas nama organisasi ada di label entitas atau
    di nama domain/judul halaman, entitas berasal dari Indonesia, dan domain benar-benar hidup.
  - Lebih dari satu kandidat yang sama kuat = ambigu = tidak dipakai (masuk daftar periksa).
Setiap organisasi hanya dicari sekali (hasil, termasuk "tidak ketemu", disimpan di cache).
"""
from __future__ import annotations

import json
import os
import re
import socket
import urllib.parse
import urllib.request

UA = "VaksincomRansomwareTracker/1.0 (+https://www.vaksin.com/data/ransomware)"
WD_API = "https://www.wikidata.org/w/api.php"
BRAVE_API = "https://api.search.brave.com/res/v1/web/search"
INDONESIA = "Q252"

STOP = {"pt", "tbk", "persero", "cv", "the", "of", "and", "dan", "di", "co", "id", "com", "www",
        "indonesia", "indonesian", "group", "grup", "company", "corp", "inc", "ltd", "new",
        "database", "leaked", "leak", "data", "free", "ff", "operations", "platform"}
# Jenis instansi yang tanpa nama khas/wilayah tidak bisa dipastikan identitasnya.
GENERIC = {"dinas", "badan", "balai", "kantor", "pemerintah", "kabupaten", "kota", "provinsi",
           "kementerian", "universitas", "sekolah", "rumah", "sakit", "rs", "koperasi", "bank",
           "perekonomian", "rakyat", "bpr", "komunikasi", "informatika", "kesehatan", "pendidikan",
           "daerah", "umum", "nasional", "negeri", "karyawan", "police", "polri"}
# Kata deskriptif: ikut dicari, tetapi tidak wajib ada di label entitas.
DESCRIPTIVE = {"airlines", "airline", "airports", "airport", "holdings", "holding", "international",
               "systems", "services", "energy", "resources", "logistics", "shipping"}
BAD_HOSTS = re.compile(
    r"(wikipedia|wikidata|linkedin|facebook|instagram|twitter|x\.com|youtube|tiktok|glassdoor|"
    r"jobstreet|glints|kalibrr|indeed|crunchbase|bloomberg|reuters|idx\.co\.id|kompas|detik|"
    r"tempo|cnbcindonesia|cnnindonesia|liputan6|tribunnews|okezone|kontan|bisnis\.com|tokopedia|"
    r"shopee|bukalapak|google|maps\.|ransom|dnb\.com|zoominfo|opencorporates)", re.I)


def tokens(name: str) -> list[str]:
    t = re.sub(r"\(.*?\)", " ", name.lower())
    t = re.sub(r"https?://|www\.", " ", t)
    t = re.sub(r"\.(co|go|ac|or|sch|net|web|my|biz)\.id\b|\.id\b|\.com\b", " ", t)
    return [w for w in re.findall(r"[a-z0-9]+", t) if w not in STOP and len(w) > 1]


def query_name(name: str) -> str | None:
    """Teks pencarian, atau None bila nama terlalu generik/ambigu untuk dipastikan."""
    tk = tokens(name)
    distinctive = [w for w in tk if w not in GENERIC and w not in DESCRIPTIVE]
    if not distinctive:
        return None
    if len(distinctive) == 1 and len(distinctive[0]) < 4:  # mis. singkatan 2-3 huruf
        return None
    words = tk + (["indonesia"] if re.search(r"\bindonesia", name, re.I) else [])
    return " ".join(words)


def _get(url: str, headers: dict | None = None, timeout: int = 30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def host_of(url: str) -> str | None:
    if not url:
        return None
    if "//" not in url:
        url = "http://" + url
    h = (urllib.parse.urlparse(url).hostname or "").lower()
    return re.sub(r"^www\d?\.", "", h) or None


def alive(host: str) -> bool:
    try:
        socket.getaddrinfo(host, 443)
        return True
    except OSError:
        return False


def covers(name_tokens: list[str], text: str) -> bool:
    """Semua kata khas nama ada di teks (label entitas / domain / judul halaman)."""
    hay = re.sub(r"[^a-z0-9]+", " ", text.lower())
    squashed = hay.replace(" ", "")
    distinctive = [w for w in name_tokens if w not in GENERIC and w not in DESCRIPTIVE] or name_tokens
    return all((f" {w} " in f" {hay} ") or (len(w) >= 4 and w in squashed) for w in distinctive)


PLACE = re.compile(r"\b(kecamatan|kelurahan|desa|kabupaten|kota|provinsi|district|subdistrict|"
                   r"village|regency|province|city|pulau|island|sungai|river|gunung|mountain)\b", re.I)


def norm(label: str) -> str:
    return " ".join(w for w in re.findall(r"[a-z0-9]+", label.lower()) if w not in STOP)


def single_word(name_tokens: list[str]) -> str | None:
    """Kata khas tunggal bila nama hanya punya satu kata khas, selain itu None."""
    d = [w for w in name_tokens if w not in GENERIC and w not in DESCRIPTIVE]
    return d[0] if len(d) == 1 else None


def from_wikidata(name: str) -> tuple[str | None, str]:
    q = query_name(name)
    if not q:
        return None, "nama generik"
    params = {"action": "wbsearchentities", "format": "json", "language": "id", "uselang": "id",
              "type": "item", "limit": "5", "search": q}
    found = json.loads(_get(f"{WD_API}?{urllib.parse.urlencode(params)}")).get("search", [])
    ids = [x["id"] for x in found]
    if not ids:
        return None, "tidak ada di basis data publik"
    ents = json.loads(_get(f"{WD_API}?" + urllib.parse.urlencode({
        "action": "wbgetentities", "format": "json", "props": "claims|labels|aliases|descriptions",
        "languages": "id|en", "ids": "|".join(ids)}))).get("entities", {})
    tk = tokens(name)
    cands = []
    for i in ids:
        e = ents.get(i, {})
        c = e.get("claims", {})
        country = {s["mainsnak"].get("datavalue", {}).get("value", {}).get("id") for s in c.get("P17", [])}
        if INDONESIA not in country:
            continue
        labels = [v["value"] for v in e.get("labels", {}).values()]
        labels += [a["value"] for lst in e.get("aliases", {}).values() for a in lst]
        descs = " ".join(v["value"] for v in e.get("descriptions", {}).values())
        # wilayah administratif (kecamatan/desa/kabupaten) bukan organisasi korban
        if PLACE.search(descs) and not PLACE.search(name):
            continue
        if single_word(tk):
            # nama satu kata (mis. "Samudera") hanya diterima bila labelnya persis sama
            if not any(norm(lab) == single_word(tk) for lab in labels):
                continue
        elif not any(covers(tk, lab) for lab in labels):
            continue
        sites = [s["mainsnak"].get("datavalue", {}).get("value") for s in c.get("P856", [])]
        hosts = sorted({h for h in map(host_of, sites) if h})
        if hosts:
            cands.append(hosts[0])
    cands = sorted(set(cands))
    if len(cands) == 1 and alive(cands[0]):
        return cands[0], "basis data publik"
    return None, "ambigu" if len(cands) > 1 else "tanpa situs resmi tercatat"


def _title(host: str) -> str:
    try:
        html = _get(f"https://{host}/", timeout=20)[:200_000].decode("utf-8", "ignore")
        m = re.search(r"<title[^>]*>(.*?)</title>", html, re.I | re.S)
        return re.sub(r"\s+", " ", m.group(1)) if m else ""
    except Exception:  # noqa: BLE001
        return ""


def from_search(name: str) -> tuple[str | None, str]:
    key = os.environ.get("BRAVE_API_KEY", "").strip()
    if not key:
        return None, "pencarian tidak aktif"
    q = query_name(name)
    if not q:
        return None, "nama generik"
    params = {"q": f"{q} situs resmi", "country": "ID", "count": "10", "search_lang": "id"}
    data = json.loads(_get(f"{BRAVE_API}?{urllib.parse.urlencode(params)}",
                           headers={"X-Subscription-Token": key, "Accept": "application/json"}))
    tk = tokens(name)
    cands = []
    for r in (data.get("web", {}) or {}).get("results", [])[:10]:
        h = host_of(r.get("url", ""))
        if not h or BAD_HOSTS.search(h):
            continue
        # domain sendiri harus mencerminkan nama; judul hasil saja tidak cukup
        if covers(tk, h.split(".")[0].replace("-", " ")) or covers(tk, h.replace(".", " ")):
            cands.append(h)
    cands = list(dict.fromkeys(cands))
    roots = sorted({re.sub(r"^[^.]+\.(?=[^.]+\.(co|go|ac|or)\.id$)", "", h) for h in cands})
    if len(roots) == 1 and alive(cands[0]) and covers(tk, _title(cands[0]) + " " + cands[0]):
        return cands[0], "mesin pencari"
    return None, "ambigu" if len(roots) > 1 else "tidak ketemu"


def resolve(name: str) -> tuple[str | None, str]:
    """(domain, sumber/alasan). Sumber publik: 'basis data publik' / 'mesin pencari'."""
    reasons = []
    for fn in (from_wikidata, from_search):
        try:
            d, why = fn(name)
        except Exception as e:  # noqa: BLE001
            d, why = None, f"galat: {type(e).__name__}"
        if d:
            return d, why
        reasons.append(why)
    return None, "; ".join(reasons)
