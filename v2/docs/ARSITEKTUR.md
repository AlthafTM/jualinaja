# Arsitektur

## Kenapa satu file server

`app/server.py` adalah satu file ~900 baris tanpa dependensi. Untuk pasar barang bekas
skala satu kota, satu proses Python + SQLite jauh lebih murah dirawat daripada
framework + Postgres. Kalau nanti perlu naik skala, batas alaminya jelas: query ada di
satu tempat, skema ada di satu string `SCHEMA`, dan tidak ada ORM yang menyembunyikan
bentuk SQL-nya.

## Lapisan

```
HTTP  →  Handler._dispatch   routing: /api/* JSON, /p/<id> HTML OG, /uploads/* foto, sisanya statis
       →  Handler._api        endpoint per sumber daya, validasi inline
       →  connect()           SQLite per request (WAL, busy_timeout 8s)
```

Tidak ada state di memori proses selain koneksi. Restart server tidak menghilangkan
apa pun; semua state ada di `data/jualinaja.db`.

## Keputusan

| Keputusan | Alasan | Konsekuensi |
|---|---|---|
| SQLite + WAL | nol operasi, backup `.backup` aman saat hidup | satu penulis pada satu waktu |
| PBKDF2 240k | stdlib, tanpa dependensi kripto | verifikasi ~80ms per login |
| Cookie `sid` HttpOnly | tidak bisa dibaca JS, tahan XSS pencurian sesi | perlu CSRF token untuk form lintas situs |
| Tawaran unik per (barang, pembeli) | mencegah spam tawaran | tawar ulang memperbarui, bukan menumpuk |
| Ulasan butuh tawaran `accepted` | ulasan hanya dari pembeli nyata | tidak ada ulasan palsu |
| `/p/<id>` dirender server | pratinjau tautan di WhatsApp butuh OG tags | satu jalur render tambahan |
| Escaping manual di klien | tanpa framework, `esc()` dipakai di setiap interpolasi | wajib disiplin di kode baru |

## Keamanan

- Semua SQL memakai parameter `?`. Tidak ada string query yang dirangkai dari input.
- Path traversal diperiksa dengan `Path.relative_to` sebelum menyajikan file.
- Unggahan dibatasi 8 MB, hanya MIME gambar, nama file diacak `secrets.token_hex`.
- `X-Content-Type-Options: nosniff` dan `Referrer-Policy: same-origin` di setiap respons.
- Otorisasi diperiksa per objek: pemilik listing, penjual untuk tawaran, moderator untuk laporan.

## Yang sengaja belum ada

Pembayaran, pengiriman, verifikasi email, reset kata sandi, rate limit, dan UI moderasi
penuh. Semua itu keputusan sadar untuk versi ini, bukan yang terlewat.
