#!/usr/bin/env python3
"""
Vaksincom — Pelacak Ransomware Indonesia (pengambil data otomatis)

Sumber data: RansomLook (https://www.ransomlook.io), lisensi CC BY 4.0.
Dijalankan terjadwal oleh GitHub Actions. Hasil publik: docs/data/ransomware-id.json

Cara kerja:
  1. Ambil daftar unggahan terbaru semua grup  (/api/posts?days=N)
  2. Untuk grup yang punya unggahan baru, ambil detail grup (/api/group/<nama>)
     supaya kolom 'description' bisa dipakai mengenali korban Indonesia.
  3. Klasifikasi: KUAT (otomatis tampil)  /  LEMAH (masuk review.json, tidak tampil).
  4. Hitung statistik dan tulis JSON untuk halaman vaksin.com.

Pemakaian:
  python scripts/update.py                  # mode rutin (3 hari terakhir)
  python scripts/update.py --days 365       # isi ulang (backfill) 12 bulan
"""
import argparse
import hashlib
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

API = "https://www.ransomlook.io/api"
UA = "VaksincomRansomwareTracker/1.0 (+https://www.vaksin.com/data/ransomware)"
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "docs" / "data"
STATE = ROOT / "state"
CONFIG = ROOT / "config"

# ---------------------------------------------------------------- deteksi Indonesia
TLD_ID = r"\b[a-z0-9-]+\.(?:co|go|ac|or|sch|net|web|my|biz|mil|desa|ponpes)\.id\b"
STRONG_TITLE = [
    re.compile(TLD_ID, re.I),
    re.compile(r"\b[a-z0-9-]{2,}\.id\b(?![\w.])", re.I),
    re.compile(r"\bindonesi(?:a|an|a's)\b", re.I),
    re.compile("\U0001F1EE\U0001F1E9"),  # bendera 🇮🇩
    re.compile(r"\bTbk\b"),
    re.compile(r"\bPT\.?\s+[A-Z][A-Za-z]"),
    re.compile(r"\b(?:Kementerian|Kabupaten|Pemerintah Kota|Pemkab|Pemkot|Pemprov|Universitas|"
               r"Rumah Sakit|Koperasi|Bank Perekonomian Rakyat|BPR|Polri|Dinas|Badan|Balai|"
               r"Politeknik|Sekolah|Pesantren|Perum|Persero)\b"),
]
STRONG_DESC = [
    re.compile(TLD_ID, re.I),
    re.compile(r"\b(?:headquartered|based|located|incorporated|registered|operating)\s+in\s+[^.\n]{0,40}\bindonesia\b", re.I),
    re.compile(r"\bindonesia(?:n)?[- ](?:based|company|state[- ]owned|government|ministry|bank|university|"
               r"hospital|firm|manufacturer|subsidiary|agency|school|insurer|retailer|operator|regional)", re.I),
    re.compile(r"\b(?:jakarta|surabaya|bandung|medan|semarang|makassar|batam|tangerang|bekasi|bogor|depok|"
               r"denpasar|yogyakarta|balikpapan|palembang|pekanbaru|samarinda|malang|cikarang|karawang)"
               r"(?:,\s*[a-z ]{0,25})?,?\s+indonesia\b", re.I),
    re.compile(r"\bPT\s+[A-Z][A-Za-z]+[^.\n]{0,60}\bTbk\b"),
    re.compile(r"\+62[\s-]?\d"),
    re.compile(r"\bIDX\s*:|\bBursa Efek Indonesia|\bIndonesia Stock Exchange", re.I),
    re.compile(r"\bBUMN\b|\b(?:PT|Perum)\s+[^.\n]{0,40}\(Persero\)"),
    # format terstruktur, mis. "Port logistics · Indonesia" / "Country: Indonesia"
    re.compile(r"[·•|]\s*Indonesia\s*(?:$|[\n·•|])", re.I | re.M),
    re.compile(r"\b(?:country|location|negara)\s*[:=]\s*Indonesia\b", re.I),
    # "X is an Indonesian renewable-energy company", "one of the Indonesian ..."
    re.compile(r"\b(?:is|are|was)\s+(?:an?\s+|one of the\s+)?(?:[\w-]+\s+){0,3}Indonesian\b", re.I),
    re.compile(r"\bone of (?:the\s+)?(?:largest\s+|leading\s+|biggest\s+)?Indonesian\b", re.I),
]
WEAK_DESC = [re.compile(r"\bindonesi(?:a|an)\b", re.I)]


def classify(title, desc, overrides):
    t, d = title or "", desc or ""
    for rx in overrides["exclude"]:
        if rx.search(t):
            return None
    for rx in overrides["include"]:
        if rx.search(t):
            return "manual"
    if any(rx.search(t) for rx in STRONG_TITLE):
        return "auto-judul"
    if any(rx.search(d) for rx in STRONG_DESC):
        return "auto-deskripsi"
    if any(rx.search(d) for rx in WEAK_DESC):
        return "lemah"
    return None


# ---------------------------------------------------------------- utilitas
def http_json(url, timeout=180, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(5 * (i + 1))
    raise RuntimeError(f"gagal ambil {url}: {last}")


def parse_dt(s):
    s = (s or "").strip().replace(" ", "T").rstrip("Z")
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        dt = datetime.fromisoformat(s[:19])
    return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt.astimezone(timezone.utc)


def load(path, default):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return default


def save(path, obj, compact=False):
    path.parent.mkdir(parents=True, exist_ok=True)
    txt = json.dumps(obj, ensure_ascii=False, separators=(",", ":")) if compact \
        else json.dumps(obj, ensure_ascii=False, indent=1)
    path.write_text(txt + "\n", encoding="utf-8")


ONION = re.compile(r"\S+\.onion\S*", re.I)
URL = re.compile(r"https?://\S+", re.I)


def clean_title(t):
    t = ONION.sub("", t or "")
    t = URL.sub(lambda m: urllib.parse.urlparse(m.group(0)).netloc, t)
    t = re.sub(r"\s+", " ", t).strip()
    return t[:140]


def org_key(title):
    """Kunci normalisasi agar 1 organisasi yang diklaim beberapa kali dihitung sekali."""
    t = title.lower()
    t = re.sub(r"\(.*?\)", " ", t)
    t = t.replace("\U0001F1EE\U0001F1E9", " ")
    t = re.sub(r"https?://", "", t)
    t = re.sub(r"^www\.", "", t.strip())
    t = re.sub(r"\.(co|go|ac|or|sch|net|web|my|biz|mil)\.id\b|\.id\b|\.com\b|\.net\b|\.org\b", " ", t)
    t = re.sub(r"\b(pt|tbk|persero|cv|the|inc|ltd)\b\.?", " ", t)
    t = re.sub(r"[^a-z0-9]+", " ", t)
    return " ".join(t.split()) or title.lower()


DOMAIN_RX = re.compile(r"\b((?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:[a-z]{2,24}))\b", re.I)
NOT_SITE = re.compile(r"(\.onion$|^(?:www\.)?(?:gmail|yahoo|hotmail|outlook|google|linkedin|facebook|instagram|twitter|x|"
                      r"youtube|wikipedia|t\.me|telegram|tox|session|mega|gofile|github)\.|\.(?:png|jpe?g|pdf|zip|rar|7z|txt|csv|xlsx?|docx?|sql|bak)$)", re.I)
TLDS_OK = re.compile(r"\.(?:[a-z]{2}|com|net|org|asia|biz|info|tech|group|app|edu|gov|online|site|store|shop)$", re.I)


def find_domain(title, desc):
    """Situs organisasi: dari judul dulu, lalu deskripsi (utamakan .id)."""
    def cands(text):
        out = []
        for m in DOMAIN_RX.finditer(text or ""):
            d = m.group(1).lower().strip(".")
            d = re.sub(r"^www\.", "", d)
            if "." not in d or NOT_SITE.search(d) or not TLDS_OK.search(d) or re.fullmatch(r"[\d.]+", d):
                continue
            out.append(d)
        return out
    t = cands(title)
    if t:
        return t[0], "judul"
    d = cands(desc)
    if d:
        best = sorted(enumerate(d), key=lambda ix: (not ix[1].endswith(".id"), ix[0]))[0][1]
        return best, "deskripsi"
    return None, None


def _same_claim(a, b):
    """Klaim yang sama dari kelompok yang sama (judul bisa beda: 'NEW', '(FF)', 'Database Leaked')."""
    if a["group"] != b["group"]:
        return False
    da, db_ = parse_dt(a["date"]), parse_dt(b["date"])
    if abs((da - db_).days) > 45:
        return False
    ka, kb = a["org"], b["org"]
    if not re.search(r"[a-z]", ka) or not re.search(r"[a-z]", kb):  # judul tanpa nama, mis. bendera saja
        return da.date() == db_.date()
    short, long_ = sorted((ka, kb), key=len)
    if len(short) < 3:
        return False
    return short == long_ or re.search(rf"(?:^| ){re.escape(short)}(?: |$)", long_) is not None


def merge_dupes(victims):
    """Gabungkan klaim ganda. Entri kurasi/manual menang (judulnya sudah dirapikan);
    domain dari entri otomatis diwariskan bila entri yang dipertahankan belum punya."""
    rank = {"manual": 0, "kurasi": 1}
    ordered = sorted(victims, key=lambda v: (rank.get(v.get("via"), 2), v["date"]))
    kept = []
    for v in ordered:
        twin = next((k for k in kept if _same_claim(k, v)), None)
        if twin is None:
            kept.append(v)
        elif v.get("domain") and not twin.get("domain"):
            twin["domain"], twin["domain_via"] = v["domain"], v.get("domain_via")
    return kept


def vid(group, title, date):
    return hashlib.sha1(f"{group}|{title}|{date[:10]}".encode()).hexdigest()[:12]


# ---------------------------------------------------------------- utama
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--max-groups", type=int, default=400)
    ap.add_argument("--no-fetch", action="store_true", help="hanya hitung ulang dari state (uji lokal)")
    args = ap.parse_args()
    now = datetime.now(timezone.utc)

    victims = load(STATE / "victims.json", [])
    seen = load(STATE / "seen.json", {})
    review = load(STATE / "review.json", [])
    global_daily = load(STATE / "global_daily.json", {})
    ov_raw = load(CONFIG / "overrides.json", {"include": [], "exclude": []})
    overrides = {k: [re.compile(p, re.I) for p in ov_raw.get(k, [])] for k in ("include", "exclude")}

    # seed dari tabel lama (sekali saja)
    if not victims and (ROOT / "scripts" / "seed_old_table.txt").exists():
        for line in (ROOT / "scripts" / "seed_old_table.txt").read_text(encoding="utf-8").splitlines():
            if "|" not in line:
                continue
            d, g, t = [x.strip() for x in line.split("|", 2)]
            victims.append({"id": vid(g, t, d), "date": d + "T00:00:00Z", "group": g,
                            "title": clean_title(t), "org": org_key(t), "via": "kurasi"})
        print(f"seed: {len(victims)} baris dari tabel lama")

    # 1. unggahan terbaru semua grup
    if args.no_fetch:
        posts = []
    else:
        res = http_json(f"{API}/posts?days={args.days}")
        posts = res.get("posts", res) if isinstance(res, dict) else res
    print(f"unggahan global {args.days} hari: {len(posts)}")

    # hitungan global harian (hari pertama jendela dilewati karena parsial)
    per_day = Counter(parse_dt(p["discovered"]).date().isoformat() for p in posts)
    first_day = (now - timedelta(days=args.days)).date().isoformat()
    for day, n in per_day.items():
        if day > first_day:
            global_daily[day] = n

    known = {(v["group"], v["title"]) for v in victims}
    todo = [p for p in posts if f'{p["group_name"]}|{p["post_title"]}' not in seen]
    groups = sorted({p["group_name"] for p in todo})[: args.max_groups]
    print(f"unggahan baru dicek: {len(todo)} dari {len(groups)} grup")

    # 2. deskripsi per grup
    desc = {}
    for i, g in enumerate(groups, 1):
        try:
            j = http_json(f"{API}/group/{urllib.parse.quote(g)}")
            plist = j[1] if isinstance(j, list) and len(j) > 1 else (j.get("posts", []) if isinstance(j, dict) else [])
            for p in plist:
                desc[(g, p.get("post_title", ""))] = p.get("description") or ""
        except Exception as e:  # noqa: BLE001
            print(f"  ! grup {g}: {e}", file=sys.stderr)
        if i % 20 == 0:
            print(f"  {i}/{len(groups)} grup")
        time.sleep(1)

    # 3. klasifikasi
    added = 0
    for p in todo:
        g, t = p["group_name"], p["post_title"]
        kind = classify(t, desc.get((g, t), ""), overrides)
        seen[f"{g}|{t}"] = p["discovered"][:10]
        if kind is None:
            continue
        ct = clean_title(t)
        if kind == "lemah":
            review.append({"date": p["discovered"], "group": g, "title": ct,
                           "hint": (re.search(r".{0,80}indonesi.{0,60}", desc.get((g, t), ""), re.I) or [""])[0]})
            continue
        dom, dsrc = find_domain(t, desc.get((g, t), ""))
        if (g, ct) in known:
            for v in victims:  # lengkapi domain korban lama (mis. hasil kurasi) saat backfill
                if v["group"] == g and v["title"] == ct and not v.get("domain") and dom:
                    v["domain"], v["domain_via"] = dom, dsrc
            continue
        victims.append({"id": vid(g, ct, p["discovered"]), "date": parse_dt(p["discovered"]).isoformat().replace("+00:00", "Z"),
                        "group": g, "title": ct, "org": org_key(ct), "via": kind,
                        "domain": dom, "domain_via": dsrc})
        known.add((g, ct))
        added += 1
    print(f"korban Indonesia baru: {added}")

    # buang yang dikecualikan belakangan via overrides
    victims = [v for v in victims if not any(rx.search(v["title"]) for rx in overrides["exclude"])]

    victims = merge_dupes(victims)

    # domain: koreksi manual (config/domains.json: {"kunci org": "domain.co.id"}) menang atas otomatis
    dmap = {k: v for k, v in load(CONFIG / "domains.json", {}).items() if not k.startswith("_")}
    for v in victims:
        if v["org"] in dmap:
            v["domain"], v["domain_via"] = (dmap[v["org"]] or None), "manual"
        elif not v.get("domain"):
            d, src = find_domain(v["title"], "")
            v["domain"], v["domain_via"] = d, src

    # pangkas state lama
    cutoff = (now - timedelta(days=420)).date().isoformat()
    seen = {k: d for k, d in seen.items() if d >= cutoff}
    global_daily = {d: n for d, n in global_daily.items() if d >= cutoff}
    rv_seen, rv = set(), []
    for r in sorted(review, key=lambda x: x["date"], reverse=True):
        k = (r["group"], r["title"])
        if k not in rv_seen and r["date"][:10] >= cutoff:
            rv_seen.add(k)
            rv.append(r)
    victims.sort(key=lambda v: v["date"], reverse=True)

    save(STATE / "victims.json", victims)
    save(STATE / "seen.json", seen, compact=True)
    save(STATE / "review.json", rv)
    save(STATE / "global_daily.json", dict(sorted(global_daily.items())))

    # 4. statistik publik
    def within(days):
        lim = (now - timedelta(days=days)).isoformat()
        return [v for v in victims if v["date"] >= lim]

    y, q, m = within(365), within(90), within(30)
    lim365 = (now - timedelta(days=365)).date().isoformat()
    monthly = defaultdict(int)
    for v in y:
        monthly[v["date"][:7]] += 1
    months = []
    cur = now.replace(day=1)
    for _ in range(12):
        months.append(cur.strftime("%Y-%m"))
        cur = (cur - timedelta(days=1)).replace(day=1)
    months.reverse()

    out = {
        "generated_at": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        "source": {"name": "RansomLook", "url": "https://www.ransomlook.io", "license": "CC BY 4.0",
                   "license_url": "https://creativecommons.org/licenses/by/4.0/"},
        "latest_detection": victims[0]["date"] if victims else None,
        "stats": {
            "orgs_365": len({v["org"] for v in y}),
            "orgs_90": len({v["org"] for v in q}),
            "orgs_30": len({v["org"] for v in m}),
            "claims_365": len(y),
            "groups_365": len({v["group"] for v in y}),
            "global_365": sum(n for d, n in global_daily.items() if d >= lim365),
            "global_days_covered": sum(1 for d in global_daily if d >= lim365),
        },
        "top_groups": [{"group": g, "count": n} for g, n in Counter(v["group"] for v in y).most_common(8)],
        "monthly": [{"month": mo, "count": monthly.get(mo, 0)} for mo in months],
        "victims": [{**{k: v[k] for k in ("id", "date", "group", "title", "org")}, "domain": v.get("domain")} for v in y],
    }
    save(DATA / "ransomware-id.json", out, compact=True)
    print(f"selesai: {out['stats']}")


if __name__ == "__main__":
    main()
