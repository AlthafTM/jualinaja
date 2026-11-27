# Kontribusi

## Menjalankan

```bash
python3 app/server.py 8123
python3 tests/api_smoke.py http://127.0.0.1:8123
```

Tidak ada `pip install`. Kalau perubahanmu menambah dependensi, jelaskan alasannya di PR —
proyek ini sengaja stdlib-only.

## Aturan singkat

1. **SQL selalu pakai parameter `?`.** Tidak ada string query dari input.
2. **Setiap endpoint baru butuh test** di `tests/api_smoke.py`, termasuk kasus negatif
   (tanpa sesi, bukan pemilik, input tidak valid).
3. **Escaping di klien**: setiap nilai dinamis lewat `esc()`. Tanpa framework, ini satu-satunya yang melindungi.
4. **Otorisasi per objek**, bukan per rute. Periksa pemilik barisnya.
5. **Jangan hapus batas yang terdokumentasi** di README tanpa membicarakannya dulu.

## Gaya

- Python: stdlib, tanpa tipe generik berlebihan, nama fungsi deskriptif.
- CSS: neobrutalis — border 3px, hard shadow, tanpa `border-radius`.
- JS: tanpa framework, tanpa build step. Satu IIFE di `app.js`.
- Bahasa UI: Indonesia. Kode dan komentar: Indonesia atau Inggris, konsisten per berkas.

## Cek sebelum kirim

```bash
python3 tests/api_smoke.py http://127.0.0.1:8123
```

Harus `77 ok, 0 gagal` atau lebih.
