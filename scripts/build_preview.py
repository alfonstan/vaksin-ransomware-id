"""Gabungkan widget + data lokal jadi preview.html (hanya untuk melihat tampilan)."""
from pathlib import Path
R = Path(__file__).resolve().parent.parent
w = (R / "widget/widget.html").read_text(encoding="utf-8")
data = (R / "docs/data/ransomware-id.json").read_text(encoding="utf-8").strip()
head = '''<!DOCTYPE html><html lang="id"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Preview: Pelacak Ransomware Indonesia (Vaksincom)</title>
<style>body{margin:0;background:#050b1c;font-family:"Source Sans 3",sans-serif}
.nav{display:flex;align-items:center;justify-content:space-between;padding:14px 36px;background:#0b1230;color:#c9d0ea;font-family:"Source Sans 3","Source Sans Pro",sans-serif;font-size:16px;letter-spacing:.03em}.nav img{display:block}
.nav b{font-size:20px;letter-spacing:.02em}.nav b i{color:#f2a136;font-style:normal}.nav span{margin-left:26px;opacity:.85}
.pick{position:fixed;right:16px;bottom:16px;z-index:9;background:#0a1430ee;border:1px solid #1d3263;border-radius:12px;padding:10px 12px;color:#dfe7fb;font-size:14px;display:flex;gap:8px;align-items:center;box-shadow:0 10px 30px #0008}
.pick button{width:26px;height:26px;border-radius:50%;border:2px solid #fff3;cursor:pointer}
.pick button.on{border-color:#fff}
@media(max-width:700px){.nav span{display:none}.nav{padding:16px}.pick{right:8px;bottom:8px;font-size:12px}}
</style>
<script>(function(){var D=__DATA__;var f=window.fetch;window.fetch=function(u){if(String(u).indexOf("ransomware-intel.json")>=0){return Promise.resolve(new Response(JSON.stringify({domains:{"contoh.co.id":{scanned_at:new Date(Date.now()-2*864e5).toISOString(),rating:"danger",email_spoofable:true,categories:[{name:"Layanan terbuka berisiko",pct:25},{name:"Software usang / rentan",pct:40},{name:"Sertifikat bermasalah",pct:10},{name:"Domain bermasalah",pct:0}]}}}),{status:200}))}
if(String(u).indexOf("ransomware-id.json")>=0){D.generated_at=new Date(Date.now()-42*60e3).toISOString();if(!D._demo){D._demo=1;D.victims.unshift({id:"demo",date:new Date(Date.now()-864e5).toISOString(),group:"contoh",title:"PT Contoh Fiktif (contoh tampilan, bukan data asli)",org:"contoh",domain:"contoh.co.id"})}return Promise.resolve(new Response(JSON.stringify(D),{status:200}))}return f.apply(this,arguments)}})();</script>
</head><body>
<div class="nav"><img src="__LOGO__" alt="Logo Vaksin.com" width="168" height="52"><div><span>HOME</span><span>LAYANAN</span><span>DATA</span><span>ARTIKEL</span><span>KONTAK</span><span>SITE INTEL</span></div></div>
'''.replace("__DATA__", data)
pick = '''<div class="pick" aria-label="Pilih warna cahaya (hanya di preview)">Warna cahaya:
<button data-c="#ffd56a" class="on" style="background:#ffd56a" title="Kuning (default)"></button>
<button data-c="#ff4d5e" style="background:#ff4d5e" title="Merah"></button>
<button data-c="#6f8dff" style="background:#6f8dff" title="Biru"></button>
<button data-c="#e9f1ff" style="background:#e9f1ff" title="Putih"></button></div>
<script>document.querySelectorAll(".pick button").forEach(function(b){b.onclick=function(){document.getElementById("vkrw-host").shadowRoot.getElementById("vkrw").style.setProperty("--glow",b.dataset.c);document.querySelectorAll(".pick button").forEach(function(x){x.classList.toggle("on",x===b)})}})</script>
</body></html>'''
import base64
logo = "data:image/png;base64," + base64.b64encode((R / "preview_logo.png").read_bytes()).decode()
(R / "preview.html").write_text((head + w + pick).replace("__LOGO__", logo), encoding="utf-8")
