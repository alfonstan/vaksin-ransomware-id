# Pelacak Ransomware Indonesia: Vaksincom

Data otomatis untuk https://www.vaksin.com/data/ransomware

- `scripts/update.py` dijalankan GitHub Actions setiap 6 jam. Skrip ini mengambil unggahan terbaru dari [RansomLook](https://www.ransomlook.io) (CC BY 4.0), mengenali korban Indonesia, lalu menulis `docs/data/ransomware-id.json`.
- GitHub Pages menyajikan file itu di `https://alfonstan.github.io/vaksin-ransomware-id/data/ransomware-id.json`.
- `widget/widget.html` adalah kode yang ditempel ke widget HTML di Duda.

## Perawatan
- **Kandidat ragu-ragu** (deskripsi hanya menyebut Indonesia sambil lalu) masuk ke `state/review.json` dan tidak tampil di halaman.
- **Aturan publikasi alamat situs korban**: alamat hanya tampil bila diumumkan sendiri oleh pelaku (judul/deskripsi unggahan, `domain_src = "unggahan"`). Alamat hasil pencarian/basis data publik/koreksi manual adalah *temuan Vaksincom* dan disimpan **privat** di folder `private/` (di-`.gitignore`; di GitHub Actions dipulihkan lewat cache): `site_lookup.json`, `domains.json` (koreksi manual `{"kunci org": "domain"}`), dan `site_private.json` (id korban → alamat + asal, dibaca portal Site Intel). Yang tampil publik ditentukan fungsi `public_domain()` di `scripts/update.py`, bukan ingatan.
- **Menambah atau menyembunyikan** korban: isi `config/overrides.json`. `include` dipakai untuk korban yang pasti Indonesia, `exclude` untuk yang salah terdeteksi. Polanya berupa regex judul unggahan.
- **Mengisi ulang 12 bulan**: buka tab Actions, pilih workflow "Update data ransomware Indonesia", klik Run workflow, lalu isi days = 365.
- **Mengganti warna cahaya**: di `widget/widget.html`, ubah `--glow`.
