# JualinAja

Pasar barang bekas antar warga: orang bisa menjual barang miliknya, dan bisa menulis
barang yang sedang dicari beserta rentang harganya.

Satu server Python tanpa dependensi. Frontend HTML/CSS/JS tanpa framework.

```bash
python3 app/server.py 8123
# buka http://127.0.0.1:8123
```

## Yang bisa dilakukan

- **Jual** — pasang barang dengan sampai 10 foto, harga, kondisi, kategori, dan kota.
- **Cari** — jelajah dengan filter kata kunci, kota, kategori, kondisi, dan rentang harga;
  urutkan berdasarkan terbaru, termurah, termahal, atau paling dilihat.
- **Minta** — tulis barang yang sedang dicari beserta rentang budget di papan cari.
- **Tawar** — kirim tawaran harga; penjual menerima satu, sisanya otomatis ditolak.
- **Chat** — percakapan per barang, dengan hitungan belum dibaca.
- **Ulasan** — bintang 1–5, hanya setelah tawaran diterima, sekali per barang.
- **Simpan** — tandai barang untuk dilihat nanti.
- **Lapor & blokir** — laporan masuk ke moderator; blokir menyembunyikan barang dan pesan.
- **Notifikasi** — tawaran, pesan, ulasan masuk ke dasbor.

## Akun demo

Semua kata sandinya `demo1234`:

```
rangga.putra@example.com      sri.wahyuni@example.com
dimas.wibowo@example.com      laras.ayu@example.com
agus.pramana@example.com      bayu.setiawan@example.com
adit.nugroho@example.com      fajar.ramadhan@example.com
moderator@example.com         ← role moderator, bisa lihat laporan
```

## Struktur

```
app/
  server.py          server HTTP + API JSON + SQLite (satu file, stdlib)
  assets/app.js      klien: setiap halaman memanggil yang dibutuhkannya
  assets/styles.css  neobrutalis: border 3px, hard shadow, tanpa sudut bulat
  index.html         beranda: paling dilihat + baru masuk + statistik
  jelajah.html       filter dan paginasi
  listing.html       detail, tawaran, chat, ulasan
  jual.html          form pasang barang + unggah foto
  cari.html          papan cari + form permintaan
  akun.html          dasbor: barang saya, tersimpan, notifikasi
  masuk.html         masuk / daftar
  bantuan.html privasi.html syarat.html 404.html
tests/api_smoke.py   77 pemeriksaan API (positif + negatif)
deploy/              systemd, Caddy, backup
data/                basis data SQLite + foto (tidak masuk git)
docs/                catatan arsitektur dan keputusan
```

## Data

SQLite dengan WAL dan foreign keys. Tabel: `users`, `sessions`, `listings`, `photos`,
`wanted`, `offers`, `messages`, `reviews`, `reports`, `blocks`, `saved`, `searches`,
`notifications`.

Kata sandi: PBKDF2-HMAC-SHA256, 240.000 iterasi, salt acak 16 byte, dibandingkan
dengan `hmac.compare_digest`. Sesi: cookie `sid` HttpOnly, SameSite=Lax, 30 hari.

## Uji

```bash
python3 app/server.py 8123 &
python3 tests/api_smoke.py http://127.0.0.1:8123
# 77 ok, 0 gagal
```

Test menutup juga kasus negatif: tanpa sesi, bukan pemilik, email duplikat, kategori
asing, harga tidak valid, foto bukan gambar, path traversal, tawaran ke barang sendiri,
ulasan ganda, dan moderator-only.

## Batas yang diketahui

- Autentikasi demo: belum ada verifikasi email, reset kata sandi, atau rate limit login.
- Laporan tersimpan tapi belum ada UI moderasi penuh (endpoint `GET /api/moderation/reports` sudah ada).
- Belum ada pembayaran, pengiriman, atau notifikasi push.
- EXIF foto belum dihapus otomatis.
- Hanya API yang punya cakupan otomatis; alur UI diverifikasi manual di browser.
